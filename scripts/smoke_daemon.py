"""D39-A runtime acceptance (D39-PRE Task E11): the real daemon, in its own process.

Everything is driven through the installed ``comms`` binary, the admin Unix socket, the stdio
proxy under a real MCP client, and HTTP ``/mcp`` with fresh ``cml1`` leases. The daemon is
``comms selftest-daemon``: the production daemon with deterministic local providers injected
(the seam). Nothing here imports the composition; each check returns ``True`` or a reason.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

COMMS = str(Path(sys.executable).parent / "comms")
PROTOCOL = "2026-07-28"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Daemon:
    """One production-shaped state directory and its selftest daemon process."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.state, self.run = root / "state", root / "run"
        self.run.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.port = _free_port()
        self.env = {**os.environ, "TELEGRAM_MCP_RUNTIME_DIR": str(self.run)}
        self.proc: subprocess.Popen[str] | None = None

    def comms(self, *argv: str, stdin: Any = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [COMMS, *argv],
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
            stdin=stdin if stdin is not None else subprocess.DEVNULL,
        )

    def json(self, *argv: str) -> Any:
        done = self.comms(*argv)
        if done.returncode != 0:
            raise AssertionError(f"comms {' '.join(argv)}: {done.stderr.strip()[:300]}")
        return json.loads(done.stdout)

    def settings(self, **extra: Any) -> None:
        path = self.state / "comms" / "comms.json"
        path.write_text(json.dumps({"local_port": self.port, **extra}), encoding="utf-8")
        path.chmod(0o600)

    def tty(self, *argv: str, secret: str) -> subprocess.CompletedProcess[str]:
        """One ``comms`` command whose hidden prompt is answered on a real terminal: a pty
        becomes the child's controlling terminal, so ``getpass`` reads it with echo off."""
        import fcntl
        import pty
        import termios

        master, slave = pty.openpty()

        def controlling() -> None:
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        try:
            proc = subprocess.Popen(
                [COMMS, *argv], env=self.env, stdin=slave, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, preexec_fn=controlling,  # noqa: PLW1509
            )  # fmt: skip
            os.close(slave)
            slave = -1
            # getpass flushes typed-ahead input when it turns echo off, so type only once its
            # prompt is on the terminal
            import select

            seen, deadline = b"", time.monotonic() + 60
            while b"not echoed" not in seen and time.monotonic() < deadline:
                if select.select([master], [], [], 0.2)[0]:
                    try:
                        seen += os.read(master, 1024)
                    except OSError:
                        break
                if proc.poll() is not None:
                    break
            time.sleep(0.1)
            os.write(master, (secret + "\n").encode())
            out, err = proc.communicate(timeout=90)
        finally:
            for fd in (master, slave):
                if fd >= 0:
                    os.close(fd)
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)

    def start(self, *, wait: bool = True) -> subprocess.Popen[str]:
        self.proc = subprocess.Popen(
            [
                COMMS,
                "selftest-daemon",
                "--state-dir",
                str(self.state),
                "--runtime-dir",
                str(self.run),
            ],
            env=self.env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if wait:
            for _ in range(600):
                if self.proc.poll() is not None:
                    raise AssertionError(f"daemon exited: {self.proc.stderr.read()[-300:]}")  # type: ignore[union-attr]
                if (self.run / "admin.sock").exists() and self._listening():
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("the daemon did not start")
        return self.proc

    def _listening(self) -> bool:
        with socket.socket() as s:
            return s.connect_ex(("127.0.0.1", self.port)) == 0

    def stop(self, sig: int = signal.SIGTERM) -> int:
        assert self.proc is not None
        self.proc.send_signal(sig)
        return int(self.proc.wait(timeout=30))

    async def mcp(self, seed: Path, action: Any) -> Any:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command=COMMS,
            args=["mcp", "--stdio", "--client-seed", str(seed), "--daemon",
                  f"http://127.0.0.1:{self.port}", "--runtime-dir", str(self.run)],
            env=self.env,
        )  # fmt: skip
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            return await action(session)

    def http(self, seed: Path, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """One tools/call over HTTP with a freshly minted cml1 lease (A33)."""
        import httpx

        from comms.cli import _hello
        from comms.core.auth import lease_format

        client, raw = lease_format.read_helper(seed)
        lease = lease_format.mint(raw, client, _hello(str(self.run))(), now=datetime.now(UTC))
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments,
                       "_meta": {"io.modelcontextprotocol/protocolVersion": PROTOCOL,
                                 "io.modelcontextprotocol/clientCapabilities": {}}},
        }  # fmt: skip
        headers = {
            "Mcp-Protocol-Version": PROTOCOL,
            "Mcp-Method": "tools/call",
            "Mcp-Name": name,
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {lease}",
        }
        response = httpx.post(
            f"http://127.0.0.1:{self.port}/mcp", json=body, headers=headers, timeout=30
        )
        result: dict[str, Any] = response.json()["result"]
        return result


def _until(predicate: Any, *, seconds: float = 15.0) -> bool:
    for _ in range(int(seconds / 0.1)):
        if predicate():
            return True
        time.sleep(0.1)
    return bool(predicate())


def drive_install_and_surfaces(root: Path) -> dict[str, Any]:
    """E11a: install, the write hold, the cutover, the doctor, clients, reads, writes, replay,
    audit, the refusals, and the three ways a daemon stops (SIGTERM, kill -9, a stale anchor)."""
    out: dict[str, Any] = {}
    d = Daemon(root / "main")
    provisioned = d.json(
        "keys", "provision", "--state-dir", str(d.state), "--runtime-dir", str(d.run)
    )
    db = d.state / "comms" / "comms.db"
    out["provision"] = (
        "comms-db-key" in provisioned["provisioned"]
        and db.read_bytes()[:16] != b"SQLite format 3\x00"
    )
    d.settings()
    d.start()
    try:
        d.json("client", "add", "--name", "smoke", "--helper-path", str(root / "seed"))
        seed = root / "seed"

        async def held(session: Any) -> Any:
            read = await session.call_tool("comms_location_list", {})
            write = await session.call_tool("comms_location_create",
                                             {"name": "Held", "request_id": "req_" + "h" * 26})  # fmt: skip
            return read, write

        read, write = asyncio.run(d.mcp(seed, held))
        out["held"] = (
            (not read.is_error)
            and write.is_error
            and (write.structured_content["error"]["code"] == "AUDIT_INTEGRITY_DEGRADED")
        )
        cut = d.json("cutover", "run")
        out["cutover"] = cut == {"phase": "COMPLETE", "writes_released": True}

        def doctor_ok() -> bool:
            return bool(d.json("doctor", "--state-dir", str(d.state))["ok"])

        out["doctor"] = _until(doctor_ok)

        async def listed(session: Any) -> Any:
            return [t.name for t in (await session.list_tools()).tools]

        from comms.mcp.catalog import TOOL_CATALOG

        out["stdio_tools"] = asyncio.run(d.mcp(seed, listed)) == [s.name for s in TOOL_CATALOG]

        async def flagged(session: Any) -> Any:  # proposed A49: the host's prompt flag
            tools = (await session.list_tools()).tools
            return {
                t.name for t in tools if (t.meta or {}).get("anthropic/requiresUserInteraction")
            }

        out["stdio_meta"] = asyncio.run(d.mcp(seed, flagged)) == {
            s.name for s in TOOL_CATALOG if s.requires_user_interaction
        }

        async def reading(session: Any) -> Any:
            return await session.call_tool("comms_location_list", {})

        got = asyncio.run(d.mcp(seed, reading))
        out["stdio_read"] = (not got.is_error) and "items" in got.structured_content
        request = "req_" + "s" * 26
        first = d.http(seed, "comms_location_create", {"name": "Parramatta", "request_id": request})
        out["http_write"] = (not first["isError"]) and first["structuredContent"][
            "location"
        ].startswith("loc_")
        again = d.http(seed, "comms_location_create", {"name": "Parramatta", "request_id": request})
        listing = d.http(seed, "comms_location_list", {})["structuredContent"]["items"]
        out["replay"] = (
            again["structuredContent"]["location"] == first["structuredContent"]["location"]
            and again["structuredContent"]["replayed"] is True
            and [i["name"] for i in listing].count("Parramatta") == 1
        )
        report = d.json("audit", "verify", "--all")
        out["verify_all"] = report == {
            "ok": True,
            "legacy": "ok",
            "lineage": "ok",
            "comms": "ok",
            "problems": [],
        }
        second = subprocess.run(
            [COMMS, "selftest-daemon", "--state-dir", str(d.state), "--runtime-dir", str(d.run)],
            env=d.env, capture_output=True, text=True, timeout=60, check=False,
        )  # fmt: skip
        out["second_daemon"] = second.returncode != 0 and "already running" in second.stderr
        no_tty = d.comms("credential", "set", "telegram-bot-token", stdin=subprocess.PIPE)
        out["credential_no_tty"] = no_tty.returncode != 0 and "interactively" in no_tty.stderr
        stale_anchor = (d.state / "comms" / "anchor" / "head.anchor").read_bytes()
        d.http(seed, "comms_location_create", {"name": "After", "request_id": "req_" + "t" * 26})

        out["sigterm"] = d.stop() == 0 and not (d.run / "admin.sock").exists()
        d.start()
        out["restart_clean"] = (
            _until(doctor_ok) and d.json("audit", "verify", "--all")["ok"] is True
        )
        d.http(seed, "comms_location_create", {"name": "Mid", "request_id": "req_" + "k" * 26})
        d.stop(signal.SIGKILL)  # no cleanup at all
        d.start()
        out["kill9_restart"] = d.json("audit", "verify", "--all")["ok"] is True and _until(
            doctor_ok
        )
        d.stop()

        anchor = d.state / "comms" / "anchor" / "head.anchor"
        anchor.write_bytes(stale_anchor)  # the anchor falls behind the chain head
        d.start()
        stale_read = d.http(seed, "comms_location_list", {})
        stale_write = d.http(
            seed, "comms_location_create", {"name": "X", "request_id": "req_" + "x" * 26}
        )
        repaired = d.json("audit", "repair")
        healed = d.http(
            seed, "comms_location_create", {"name": "Y", "request_id": "req_" + "y" * 26}
        )
        out["stale_anchor"] = (
            not stale_read["isError"]
            and stale_write["isError"]
            and stale_write["structuredContent"]["error"]["code"] == "AUDIT_INTEGRITY_DEGRADED"
            and repaired["repaired"] is True
            and not healed["isError"]
        )
    finally:
        if d.proc is not None and d.proc.poll() is None:
            d.stop()

    wrong = Daemon(root / "wrong")
    wrong.json(
        "keys", "provision", "--state-dir", str(wrong.state), "--runtime-dir", str(wrong.run)
    )
    wrong.settings()
    key = next((wrong.state / "comms" / "secrets" / "comms-db-key").iterdir())
    key.write_bytes(os.urandom(32))
    proc = wrong.start(wait=False)
    code = proc.wait(timeout=60)
    stderr = proc.stderr.read() if proc.stderr else ""
    out["wrong_key"] = (
        code != 0 and "does not open comms.db" in stderr and not (wrong.run / "admin.sock").exists()
    )
    return out


def _source_backup(root: Path) -> dict[str, Any]:
    """A directory prepared elsewhere and exported as a real signed, encrypted backup."""
    from comms.core.backup import age
    from comms.core.backup.export_import import export
    from comms.core.campaigns import directory as d
    from comms.core.keys import rotate as rot
    from tests.core import schema_fixtures as fx
    from tests.core.audit.legacy_fixtures import comms_world

    now = datetime.now(UTC)
    source = root / "source"
    source.mkdir(mode=0o700)
    w = comms_world(source)
    rot.rotate(w["writer"], w["store"], "backup-key", material=os.urandom(32),
               prove=lambda m: None, now=now)  # fmt: skip
    conn = w["conn"]
    loc = d.add_location(conn, "Parramatta", now=now)
    rcp = d.add_recipient(conn, now=now, display_name="Sara")
    d.add_contact_point(conn, rcp, "whatsapp", "+61400000001", normalize=fx.wa, now=now)
    d.add_destination(conn, loc, "telegram", "channel:1234567890", "MQ Society",
                      normalize=fx.tg, now=now)  # fmt: skip
    identity = age.generate_identity()
    exported = export(w["writer"], w["store"], age.recipient_of(identity), {}, now=now)
    base = root / "restore"
    for suffix, data in ((".age", exported.ciphertext), (".sig", exported.sidecar)):
        path = base.with_suffix(suffix)
        path.write_bytes(data)
        path.chmod(0o600)
    key = root / "restore.key"
    key.write_text(identity + "\n", encoding="ascii")
    key.chmod(0o600)
    conn.close()
    return {"base": base, "key": key, "signer": exported.signer_key_id, "rcp": rcp}


def _campaign(d: Daemon, rcp: str, title: str) -> str:
    cmp = str(d.json("campaign", "create", "--title", title)["result"]["campaign"])
    d.json("campaign", "set-content", "--campaign", cmp, "--content", '{"canonical": "Salaam"}')
    d.json("campaign", "set-targets", "--campaign", cmp, "--targets",
           json.dumps({"recipients": [rcp]}), "--transports", '["whatsapp"]')  # fmt: skip
    d.json("campaign", "validate", "--campaign", cmp)
    return cmp


def _jobs(d: Daemon, cmp: str) -> dict[str, int]:
    status = d.json("campaign", "status", "--campaign", cmp)["result"]
    return dict(status.get("jobs") or {})


def drive_directory_and_campaigns(root: Path) -> dict[str, Any]:
    """E11b: a backup seeds the directory; a campaign is delivered by the daemon; a scheduled
    campaign survives kill -9 and runs once; a cursor-key rotation invalidates old cursors."""
    out: dict[str, Any] = {}
    d = Daemon(root / "dir")
    d.json("keys", "provision", "--state-dir", str(d.state), "--runtime-dir", str(d.run))
    webhook_port = _free_port()
    d.settings(webhook_port=webhook_port)
    d.start()
    try:
        d.json("cutover", "run")
        seed = root / "seed2"
        d.json("client", "add", "--name", "smoke2", "--helper-path", str(seed))
        backup = _source_backup(root)
        staged = d.json("backup", "import", "stage", "--from", str(backup["base"]), "--identity",
                        str(backup["key"]), "--trust-key", backup["signer"], "--adopt")  # fmt: skip
        committed = d.json("backup", "import", "commit", "--handle", staged["handle"])
        groups = d.http(seed, "comms_group_list", {})["structuredContent"]["items"]
        out["backup_seed"] = committed["committed"] is True and [g["name"] for g in groups] == [
            "MQ Society"
        ]

        grp = groups[0]["group"] if groups else ""

        def local_texts() -> list[str]:
            page = d.http(seed, "comms_context_recent", {"group": grp, "limit": 10})
            items = page["structuredContent"].get("items", []) if not page["isError"] else []
            return [i["untrusted_text"] for i in items if i["source"] == "telegram_local"]

        out["bot_updates_local"] = _until(lambda: len(local_texts()) == 4)  # A47: a document
        out.update(_media_checks(d, seed, grp))

        cmp = _campaign(d, backup["rcp"], "Now")
        d.json("campaign", "send", "--campaign", cmp)
        out["campaign_delivered"] = _until(
            lambda: (jobs := _jobs(d, cmp)) and "PENDING" not in jobs and sum(jobs.values()) == 1,
            seconds=30,
        )

        later = _campaign(d, backup["rcp"], "Later")
        at = datetime.fromtimestamp(time.time() + 6, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        d.json("campaign", "schedule", "--campaign", later, "--at", at)
        d.stop(signal.SIGKILL)  # before it is due
        d.start()
        out["bot_updates_no_duplicate"] = sorted(local_texts()) == [
            "selftest document",
            *(f"selftest update {n}" for n in (1, 2, 3)),
        ]  # the restart polled again from the stored offset: nothing twice
        out["scheduled_once"] = _until(
            lambda: (jobs := _jobs(d, later)) and "PENDING" not in jobs and sum(jobs.values()) == 1,
            seconds=45,
        )

        page = d.http(seed, "comms_context_recent", {"group": grp, "limit": 2})["structuredContent"]
        cursor = page["next_cursor"]
        d.json("keys", "rotate", "cursor-key")
        stale = d.http(seed, "comms_context_page", {"cursor": cursor})
        fresh = d.http(seed, "comms_context_recent", {"group": grp, "limit": 2})
        out["cursor_rotation"] = bool(cursor) and stale["isError"] and not fresh["isError"]
        out.update(_catalog_checks(d, seed, webhook_port))
        out.update(_sweep_checks(d, seed, grp))
        out["verify_after"] = d.json("audit", "verify", "--all")["ok"] is True
        out.update(_webhook_checks(d, webhook_port))
    finally:
        if d.proc is not None and d.proc.poll() is None:
            d.stop()
    return out


IG_TOKEN = "IGAAsmokeTOKENsmokeTOKENsmokeTOKEN0123456789"  # the documented token shape
IG_USER = "17841400000000099"  # the selftest daemon's scripted account (runtime/selftest.py)


def drive_instagram(root: Path) -> dict[str, Any]:
    """Proposed A49 on the real daemon: an account added at the hidden prompt, all 24 Instagram
    tools over HTTP /mcp against the selftest daemon's scripted graph.instagram.com, a replay,
    both doctors, a token refresh, the audit chain, and the account removed again."""
    import jsonschema

    from comms.core import refs
    from comms.mcp.catalog import TOOL_CATALOG

    out: dict[str, Any] = {}
    specs = {s.name: s for s in TOOL_CATALOG}
    d = Daemon(root / "ig")
    d.json("keys", "provision", "--state-dir", str(d.state), "--runtime-dir", str(d.run))
    d.settings(instagram={"default": "main", "dm_disclosure": "Sent with comms",
                          "accounts": {"main": {"label": "Smoke", "writes": True, "dms": True}}})  # fmt: skip
    d.start()
    try:
        d.json("cutover", "run")
        seed = root / "seed-ig"
        d.json("client", "add", "--name", "smoke-ig", "--helper-path", str(seed))

        def code(answer: dict[str, Any]) -> Any:
            return (answer.get("structuredContent") or {}).get("error", {}).get("code")

        before = d.http(seed, "comms_instagram_whoami", {})
        out["ig_unconfigured_before_add"] = code(before) == "NOT_CONFIGURED" or before

        added = d.tty("transport", "instagram", "account", "add", "main", secret=IG_TOKEN)
        reply = json.loads(added.stdout) if added.returncode == 0 else {}
        out["ig_account_add_hidden_prompt"] = (
            reply.get("alias") == "main" and str(reply.get("account", "")).startswith("iga_")
            and reply.get("username") == "selftest.studio" and reply.get("reloaded") is True
            and IG_TOKEN not in added.stdout + added.stderr and IG_USER not in added.stdout
        ) or f"rc={added.returncode} {added.stderr.strip()[-200:]}"  # fmt: skip
        listed = d.json("transport", "instagram", "account", "list")["accounts"]
        out["ig_account_list"] = [(a["alias"], a["configured"], bool(a["account"]))
                                  for a in listed] == [("main", True, True)] or listed  # fmt: skip

        wrong: dict[str, Any] = {}
        seen: dict[str, dict[str, Any]] = {}

        def call(name: str, arguments: dict[str, Any], **extra: Any) -> dict[str, Any]:
            spec = specs[f"comms_instagram_{name}"]
            if spec.requires_request_id:
                arguments = {"account": "main", **arguments, "request_id": refs.mint("request")}
            answer = d.http(seed, spec.name, {**arguments, **extra})
            body = dict(answer.get("structuredContent") or {})
            if answer["isError"]:
                wrong[spec.name] = code(answer)
                return {}
            try:
                jsonschema.Draft202012Validator(spec.output_schema).validate(body)
            except jsonschema.ValidationError as bad:
                wrong[spec.name] = f"output schema: {bad.message[:100]}"
            seen[spec.name] = body
            return body

        call("account_list", {})
        call("whoami", {})
        call("profile_get", {})
        media = call("media_list", {}).get("items", [{}])[0].get("media", "")
        call("media_get", {"media": media})
        call("media_insights", {"media": media, "metrics": ["reach"]})
        call("account_insights", {"metrics": ["views"], "breakdown": "follower_type"})
        story_ref = call("story_list", {}).get("items", [{}])[0].get("media", "")  # R-IG11
        call("story_insights", {"media": story_ref, "metrics": ["navigation"],
                                "breakdown": "story_navigation_action_type"})  # fmt: skip
        comment = call("comment_list", {"media": media}).get("items", [{}])[0].get("comment", "")
        call("comment_replies", {"comment": comment})
        call("tag_list", {})
        person = call("conversation_list", {}).get("items", [{}])[0].get("person", "")
        call("conversation_messages", {"person": person})
        call("publish_quota", {})
        image = {
            "kind": "image",
            "url": "https://cdn.example.com/smoke.jpg",
            "caption": "Smoke #ig",
        }
        digest = call("publish_preview", {"account": "main", "create": "container_create",
                                          **image}).get("preview_digest")  # fmt: skip
        container = call("container_create", image, preview_digest=digest).get("container")
        children = [call("container_create", {"kind": "carousel_image", "url": image["url"]})
                    .get("container") for _ in range(2)]  # fmt: skip
        call("carousel_create", {"children": children})
        published = call("publish", {"container": container})
        story = call("container_create", {"kind": "story_video", "url": image["url"]}).get(
            "container"
        )  # proposed A49, R-IG10: a Story
        shared = call("publish", {"container": story})
        call("comment_reply", {"comment": comment, "text": "Thanks!"})
        call("comment_hide", {"comment": comment, "hide": True})
        call("comments_enabled_set", {"media": media, "enabled": False})
        call("comment_delete", {"comment": comment})
        sent = call("message_send", {"person": person, "text": "Hello from the smoke"})
        names = [s.name for s in TOOL_CATALOG if s.name.startswith("comms_instagram_")]
        bad_results = {n: b.get("result") for n, b in seen.items()
                       if "result" in b and b["result"] != "SUCCEEDED"}  # fmt: skip
        out["ig_tools_end_to_end"] = (
            not wrong and not bad_results and sorted(seen) == sorted(names) and len(names) == 24
            and str(published.get("media", "")).startswith("igm_")
            and str(shared.get("media", "")).startswith("igm_")
        ) or {**wrong, **bad_results, "missing": sorted(set(names) - set(seen))}  # fmt: skip

        request_id = refs.mint("request")
        dm = {"account": "main", "person": person, "text": "Once only", "request_id": request_id}
        first = d.http(seed, "comms_instagram_message_send", dm)["structuredContent"]
        again = d.http(seed, "comms_instagram_message_send", dm)["structuredContent"]
        out["ig_replay_no_second_send"] = (
            first.get("result") == "SUCCEEDED" and again.get("replayed") is True
            and again.get("op_ref") == first.get("op_ref") and sent.get("result") == "SUCCEEDED"
        ) or [first, again]  # fmt: skip

        found = d.json("transport", "instagram", "doctor")["findings"]
        report = d.json("doctor", "--state-dir", str(d.state))
        ig_codes = [f["code"] for f in report["findings"] if f["code"].startswith("IG_")]
        out["ig_doctors"] = (
            found == [{"alias": "main", "status": "OK", "codes": []}] and ig_codes == []
        ) or [found, ig_codes]  # fmt: skip

        refreshed = d.json("transport", "instagram", "token", "refresh", "--alias", "main")
        out["ig_token_refresh"] = (
            [r.get("refreshed") for r in refreshed["results"]] == [True]
            and d.http(seed, "comms_instagram_whoami", {})["isError"] is False
        ) or refreshed  # fmt: skip

        out["ig_audit_verifies"] = d.json("audit", "verify", "--all")["ok"] is True

        removed = d.json("transport", "instagram", "account", "remove", "main")
        after = d.http(seed, "comms_instagram_whoami", {})
        out["ig_account_remove"] = (
            removed.get("token_revoked") is True and code(after) == "NOT_CONFIGURED"
        ) or [removed, code(after)]  # fmt: skip
    finally:
        if d.proc is not None and d.proc.poll() is None:
            d.stop()
    return out


WA_GROUP = "Y2FwaV9ncm91cDpTTU9LRTEyMzQ1Njc4OQ"  # a Meta-shaped (opaque) group id
SMOKE_PHONE = "61400000077"


def _signed_post(port: int, body: bytes) -> int:
    """One webhook POST signed with the selftest app secret; the status code."""
    import hashlib
    import hmac

    import httpx

    from comms.runtime.selftest import SELFTEST_APP_SECRET

    signed = "sha256=" + hmac.new(SELFTEST_APP_SECRET, body, hashlib.sha256).hexdigest()
    headers = {"content-type": "application/json", "x-hub-signature-256": signed}
    return httpx.post(
        f"http://127.0.0.1:{port}/webhooks/meta", content=body, headers=headers
    ).status_code


def _message(wamid: str, text: str, group: str | None = None) -> bytes:
    message = {"from": SMOKE_PHONE, "id": wamid, "timestamp": "1758800100", "type": "text",
               "text": {"body": text}, **({"group_id": group} if group else {})}  # fmt: skip
    return json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "1234567890"},
        "contacts": [{"wa_id": SMOKE_PHONE, "profile": {"name": "Smoke"}}],
        "messages": [message]}}]}]}).encode()  # fmt: skip


def _media_checks(d: Daemon, seed: Path, grp: str) -> dict[str, Any]:
    """A47 (H6, D39-A): a staged photo sent to the Telegram group by the bot, once, with its
    replay; and the bot's retained document paged back whole through the real downloader
    (getFile, then the file host), with its SHA-256 and type."""
    import base64
    import hashlib

    from comms.core import refs
    from comms.runtime.selftest import SELFTEST_DOCUMENT

    def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        answer = d.http(seed, name, arguments)
        return {} if answer["isError"] else dict(answer["structuredContent"])

    photo = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 300
    begun = call("comms_media_stage_begin", {
        "mime": "image/jpeg", "size": len(photo), "sha256": hashlib.sha256(photo).hexdigest(),
        "request_id": refs.mint("request")})  # fmt: skip
    step = int(begun.get("chunk_max") or 1)
    for seq, start in enumerate(range(0, len(photo), step)):
        call("comms_media_stage_chunk", {
            "upload": begun.get("upload"), "seq": seq,
            "data_b64": base64.b64encode(photo[start : start + step]).decode(),
            "request_id": refs.mint("request")})  # fmt: skip
    request = refs.mint("request")
    args = {"group": grp, "upload": begun.get("upload"), "kind": "photo", "caption": "Salaam",
            "actor": "telegram_bot", "request_id": request}  # fmt: skip
    sent, again = call("comms_message_send_media", args), call("comms_message_send_media", args)
    out = {"media_send": sent.get("result") == "SUCCEEDED"
           and str(sent.get("message", "")).startswith("cmg_") and again.get("replayed") is True}  # fmt: skip

    items = call("comms_context_recent", {"group": grp, "limit": 10}).get("items", [])
    media = next((i["media_ref"] for i in items if "media_ref" in i), None)
    got, offset, page = b"", 0, {}
    while media is not None:
        page = call("comms_media_download", {"media": media, "offset": offset})
        if not page:
            break
        piece = base64.b64decode(page["data_b64"])
        got, offset = got + piece, offset + len(piece)
        if page["complete"]:
            break
    out["media_download"] = (
        got == SELFTEST_DOCUMENT and page.get("mime") == "application/pdf"
        and page.get("sha256") == hashlib.sha256(SELFTEST_DOCUMENT).hexdigest()
    )  # fmt: skip
    return out


SWEEP_REPORT: dict[str, Any] = {}


def _sweep_checks(d: Daemon, seed: Path, grp: str) -> dict[str, Any]:
    """Every catalog tool over HTTP /mcp against the real daemon (scripts/smoke_sweep.py): a
    success valid against its output schema, or an error the tool declares; never another."""
    from smoke_sweep import sweep

    from comms.mcp.catalog import TOOL_CATALOG

    report = sweep(lambda name, arguments: d.http(seed, name, arguments), grp)
    SWEEP_REPORT.clear()
    SWEEP_REPORT.update(report)
    wrong = {name: why for name, (kind, why) in report.items() if kind == "WRONG"}
    # every tool, whatever the catalog's size (proposed A49 grows it; the pin holds the count)
    return {"catalog_sweep": not wrong and len(report) == len(TOOL_CATALOG) or wrong}


def _catalog_checks(d: Daemon, seed: Path, port: int) -> dict[str, Any]:
    """Catalog amendment G9 (D39-A): the directory, WhatsApp groups and a person's context over
    MCP against the real daemon: create a person, a WhatsApp contact, a location with the person
    in it, a Telegram and a WhatsApp group; a location campaign reaches the person; a signed
    webhook for the WhatsApp group is read by its grp_; comms_context_person serves the DM."""
    from comms.core import refs

    def call(name: str, arguments: dict[str, Any], *, write: bool = True) -> dict[str, Any]:
        extra = {"request_id": refs.mint("request")} if write else {}
        answer = d.http(seed, name, {**arguments, **extra})
        return {} if answer["isError"] else dict(answer["structuredContent"])

    out: dict[str, Any] = {}
    rcp = call("comms_directory_recipient_create", {"display_name": "Smoke Person"}).get(
        "recipient"
    )
    rct = call("comms_directory_contact_add", {"recipient": rcp, "transport": "whatsapp",
                                               "identity": f"+{SMOKE_PHONE}"}).get("contact")  # fmt: skip
    loc = call("comms_location_create", {"name": "Smoke place"}).get("location")
    member = call("comms_location_member_add", {"location": loc, "recipient": rcp})
    tg = call("comms_directory_destination_create", {"location": loc, "transport": "telegram",
                                                     "identity": "-4242", "name": "Smoke TG"})  # fmt: skip
    wa = call("comms_directory_destination_create", {"location": loc, "transport": "whatsapp",
                                                     "identity": WA_GROUP, "name": "Smoke WA"})  # fmt: skip
    listed = {g["group"] for g in call("comms_group_list", {}, write=False).get("items", [])}
    out["catalog_directory"] = (
        all(isinstance(x, str) for x in (rcp, rct, loc)) and member.get("replayed") is False
        and {tg.get("group"), wa.get("group")} <= listed and None not in (tg.get("group"), wa.get("group"))
    )  # fmt: skip

    cmp = str(d.json("campaign", "create", "--title", "Place")["result"]["campaign"])
    d.json("campaign", "set-content", "--campaign", cmp, "--content", '{"canonical": "Salaam"}')
    d.json("campaign", "set-targets", "--campaign", cmp, "--targets",
           json.dumps({"locations": [loc]}), "--transports", '["whatsapp"]')  # fmt: skip
    d.json("campaign", "validate", "--campaign", cmp)
    d.json("campaign", "send", "--campaign", cmp)
    out["catalog_location_campaign"] = _until(
        lambda: (jobs := _jobs(d, cmp)) and "PENDING" not in jobs and sum(jobs.values()) == 1,
        seconds=30,
    )

    sent = _signed_post(port, _message("wamid.GRP1", "in the group", WA_GROUP))
    sent_dm = _signed_post(port, _message("wamid.DM1", "a direct word"))

    def group_texts() -> list[str]:
        page = call("comms_context_recent", {"group": wa.get("group"), "limit": 5}, write=False)
        return [i.get("untrusted_text") for i in page.get("items", [])
                if i.get("source") == "whatsapp_webhook_archive"]  # fmt: skip

    out["catalog_whatsapp_group_context"] = sent == 200 and _until(
        lambda: group_texts() == ["in the group"]
    )

    def person_dm() -> list[str]:
        got = call("comms_context_person", {"recipient": rcp, "transports": ["whatsapp"]},
                   write=False)  # fmt: skip
        sections = {s["section"]: s for s in got.get("sections", [])}
        return [i.get("untrusted_text") for i in sections.get("whatsapp", {}).get("items", [])]

    out["catalog_context_person"] = sent_dm == 200 and _until(
        lambda: person_dm() == ["a direct word"]
    )
    return out


def _webhook_checks(d: Daemon, port: int) -> dict[str, Any]:
    """The real webhook pipeline on its own listener, with the selftest secrets."""
    import hashlib
    import hmac

    import httpx

    from comms.runtime.selftest import SELFTEST_APP_SECRET, SELFTEST_VERIFY_TOKEN

    base = f"http://127.0.0.1:{port}/webhooks/meta"
    body = json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "1234567890"},
        "contacts": [{"wa_id": "61400000001", "profile": {"name": "Sara"}}],
        "messages": [{"from": "61400000001", "id": "wamid.SMOKE", "timestamp": "1758800000",
                      "type": "text", "text": {"body": "salaam"}}]}}]}]}).encode()  # fmt: skip
    signed = "sha256=" + hmac.new(SELFTEST_APP_SECRET, body, hashlib.sha256).hexdigest()
    headers = {"content-type": "application/json", "x-hub-signature-256": signed}
    challenge = httpx.get(base, params={"hub.mode": "subscribe", "hub.verify_token": SELFTEST_VERIFY_TOKEN,
                                        "hub.challenge": "4242"})  # fmt: skip
    accepted = httpx.post(base, content=body, headers=headers)
    unsigned = httpx.post(base, content=body, headers={"content-type": "application/json"})
    out = {
        "webhook_served": challenge.status_code == 200
        and challenge.text == "4242"
        and accepted.status_code == 200
        and unsigned.status_code == 401,
    }
    httpx.post(base, content=body, headers=headers)  # a redelivery, then the process dies
    d.stop(signal.SIGKILL)
    d.start()
    out["webhook_kill9"] = d.json("audit", "verify", "--all")["ok"] is True and _until(
        lambda: bool(d.json("doctor", "--state-dir", str(d.state))["ok"])
    )
    return out


RELAY_DIR = Path(__file__).resolve().parents[1] / "relay"


def _wrangler_dev(port: int, env_file: Path, persist: Path) -> subprocess.Popen[str]:
    proc = subprocess.Popen(
        ["npx", "wrangler", "dev", "--ip", "127.0.0.1", "--port", str(port), "--env-file",
         str(env_file), "--persist-to", str(persist)],
        cwd=RELAY_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
        start_new_session=True,
    )  # fmt: skip
    ready = _until(lambda: _open(port), seconds=90)
    if not ready:
        _kill_group(proc)
        raise AssertionError("wrangler dev did not start")
    return proc


def _open(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _kill_group(proc: subprocess.Popen[str]) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=20)


def drive_relay(root: Path) -> dict[str, Any]:
    """A48 (R5): the WhatsApp relay under ``wrangler dev``, fed while the daemon is off.

    The daemon's own keys go to the Worker through the installed CLI's pipes. A signed webhook
    and an unsigned one are posted to the relay; then the daemon starts, collects, verifies,
    archives the signed one (read back over MCP, once) and quarantines the other, and the
    mailbox drains."""
    import hashlib
    import hmac

    import httpx

    from comms.core import refs, relay_sig
    from comms.runtime.selftest import SELFTEST_APP_SECRET

    out: dict[str, Any] = {}
    if not (RELAY_DIR / "node_modules" / ".bin" / "wrangler").exists():
        raise AssertionError("relay/node_modules is missing (run: cd relay && npm ci)")
    d = Daemon(root / "relay")
    d.json("keys", "provision", "--state-dir", str(d.state), "--runtime-dir", str(d.run))
    values = {
        "RELAY_PULL_KEY": d.comms("relay", "export-pull-key", "--state-dir", str(d.state)).stdout,
        "RELAY_AGE_RECIPIENT": d.comms("relay", "recipient", "--state-dir", str(d.state)).stdout,
        "RELAY_PATH_TOKEN": d.comms("relay", "new-path").stdout,
        "META_VERIFY_TOKEN": "smoke-" + refs.mint("request"),
    }
    port = _free_port()
    env_file = root / "relay.vars"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    env_file.chmod(0o600)
    wrangler = _wrangler_dev(port, env_file, root / "relay-state")
    try:
        hook = f"http://127.0.0.1:{port}/webhooks/meta/{values['RELAY_PATH_TOKEN']}"
        body = _message("wamid.RELAY1", "while you were away")
        signed = "sha256=" + hmac.new(SELFTEST_APP_SECRET, body, hashlib.sha256).hexdigest()
        forged = "sha256=" + "0" * 64
        posted = [
            httpx.post(hook, content=body, headers={"content-type": "application/json",
                                                    "x-hub-signature-256": sig}).status_code
            for sig in (signed, forged)
        ]  # fmt: skip
        d.settings(relay={"url": f"https://127.0.0.1:{port}"})
        d.start()
        d.json("cutover", "run")
        seed = root / "seed-relay"
        d.json("client", "add", "--name", "smoke-relay", "--helper-path", str(seed))

        def call(name: str, arguments: dict[str, Any], *, write: bool = True) -> dict[str, Any]:
            extra = {"request_id": refs.mint("request")} if write else {}
            answer = d.http(seed, name, {**arguments, **extra})
            return {} if answer["isError"] else dict(answer["structuredContent"])

        rcp = call("comms_directory_recipient_create", {"display_name": "Relay Person"}).get(
            "recipient"
        )
        call("comms_directory_contact_add", {"recipient": rcp, "transport": "whatsapp",
                                             "identity": f"+{SMOKE_PHONE}"})  # fmt: skip

        def person_dm() -> list[str]:
            got = call("comms_context_person", {"recipient": rcp, "transports": ["whatsapp"]},
                       write=False)  # fmt: skip
            sections = {s["section"]: s for s in got.get("sections", [])}
            return [i.get("untrusted_text") for i in sections.get("whatsapp", {}).get("items", [])]

        out["relay_offline_catchup"] = posted == [200, 200] and _until(
            lambda: person_dm() == ["while you were away"], seconds=30
        )

        key = bytes.fromhex(values["RELAY_PULL_KEY"])

        def mailbox_depth() -> int:
            pull = json.dumps({"after": 0, "limit": 50}, separators=(",", ":")).encode()
            now = int(time.time())
            answer = httpx.post(f"http://127.0.0.1:{port}/pull", content=pull, headers={
                "x-comms-timestamp": str(now),
                "x-comms-signature": relay_sig.sign(key, "POST", "/pull", now, pull)})  # fmt: skip
            return int(answer.json()["depth"])

        status = d.json("relay", "status", "--state-dir", str(d.state))
        doctor = {f["code"] for f in d.json("doctor", "--state-dir", str(d.state))["findings"]}
        out["relay_quarantine"] = (
            status["quarantined"] == 1 and status["gaps"] == 0 and status["last_error"] is None
            and "RELAY_QUARANTINE" in doctor and _until(lambda: mailbox_depth() == 0)
            and d.json("audit", "verify", "--all")["ok"] is True
        )  # fmt: skip
    finally:
        if d.proc is not None and d.proc.poll() is None:
            d.stop()
        _kill_group(wrangler)
    return out
