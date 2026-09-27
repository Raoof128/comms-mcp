"""Spec A48 (Task R2): the relay Worker's configuration, checked from the main suite.

The Worker's own behaviour is proved by ``relay/test`` (Vitest in workerd); these checks keep
D-R1 and the secret hygiene visible to the Python gate as well.
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELAY = ROOT / "relay"


def _jsonc(path: Path) -> dict:
    text = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("//"))  # fmt: skip
    return json.loads(text)


def test_the_worker_holds_no_meta_app_secret():
    config = _jsonc(RELAY / "wrangler.jsonc")
    assert config["secrets"]["required"] == [
        "RELAY_PATH_TOKEN",
        "META_VERIFY_TOKEN",
        "RELAY_PULL_KEY",
        "RELAY_AGE_RECIPIENT",
    ]
    assert "vars" not in config  # nothing is configured in the clear
    for path in (*RELAY.glob("src/*.ts"), RELAY / "wrangler.jsonc"):
        assert not re.search(r"app[_-]?secret", path.read_text(encoding="utf-8"), re.IGNORECASE), (
            path
        )


def test_the_mailbox_is_a_sqlite_durable_object():
    config = _jsonc(RELAY / "wrangler.jsonc")
    assert config["durable_objects"]["bindings"] == [{"name": "MAILBOX", "class_name": "Mailbox"}]
    assert config["migrations"] == [{"tag": "v1", "new_sqlite_classes": ["Mailbox"]}]
    assert config["observability"] == {"enabled": False}  # no request logs on Cloudflare


def test_local_secrets_and_state_never_reach_git():
    for name in ("relay/.dev.vars", "relay/.wrangler/state/x", "relay/node_modules/x",
                 "relay/worker-configuration.d.ts"):  # fmt: skip
        ignored = subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT, check=False)
        assert ignored.returncode == 0, name
    shown = subprocess.run(["git", "check-ignore", "-q", "relay/.dev.vars.example"], cwd=ROOT,
                           check=False)  # fmt: skip
    assert shown.returncode == 1


def test_dependencies_are_pinned_and_run_no_install_scripts():
    package = json.loads((RELAY / "package.json").read_text(encoding="utf-8"))
    for version in (*package["dependencies"].values(), *package["devDependencies"].values()):
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), version
    assert package["allowScripts"] and not any(package["allowScripts"].values())
    assert (RELAY / "package-lock.json").is_file()


def test_the_dev_example_holds_only_the_test_values():
    """The example's values are the fixed, test-only ones the Vitest config uses."""
    example = (RELAY / ".dev.vars.example").read_text(encoding="utf-8")
    config = (RELAY / "vitest.config.ts").read_text(encoding="utf-8")
    for line in example.splitlines():
        if line and not line.startswith("#"):
            name, _, value = line.partition("=")
            assert f'{name}: "{value}"' in config, name
