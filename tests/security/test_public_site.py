"""W-Vault's public pages (site/): the privacy policy Meta's App Dashboard links to.

Meta's privacy-policy expectations (2026): the policy is the app's own, clearly marked as a
privacy policy, reachable by crawlers (so plain HTML, no script), and says what is collected,
why, and how a person requests deletion. The Pages workflow publishes site/ alone, with every
action pinned to a commit.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
POLICY = SITE / "privacy" / "index.html"
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.tags: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
        self._in_title = tag == "title"

    def handle_data(self, data):
        if self._in_title:
            self.title += data

    def handle_endtag(self, tag):
        self._in_title = False


def _parse(path: Path) -> _Page:
    page = _Page()
    page.feed(path.read_text(encoding="utf-8"))
    return page


def test_the_policy_is_clearly_a_privacy_policy_for_this_app():
    page = _parse(POLICY)
    text = POLICY.read_text(encoding="utf-8")
    assert page.title.startswith("Privacy Policy") and "W-Vault" in page.title
    assert "1306158711456072" in text  # the Meta app it belongs to (W-Vault)
    assert "Effective" in text and "Last updated" in text


def test_the_policy_covers_what_meta_requires():
    page = _parse(POLICY)
    for section in ("collect", "use", "share", "retention", "deletion", "rights", "contact"):
        assert section in page.ids, section
    assert any(h.startswith("mailto:") for h in page.links)


def test_the_pages_need_no_script_and_track_nothing():
    for path in SITE.rglob("*.html"):
        page = _parse(path)
        assert "script" not in page.tags and "iframe" not in page.tags, path
        text = path.read_text(encoding="utf-8").lower()
        for tracker in ("googletagmanager", "google-analytics", "gtag(", "cookie="):
            assert tracker not in text, (path, tracker)


def test_every_local_link_resolves():
    for path in SITE.rglob("*.html"):
        page = _parse(path)
        for href in page.links:
            if re.match(r"^(https?:|mailto:|#)", href):
                continue
            target = (path.parent / href.split("#")[0]).resolve()
            if target.is_dir():
                target = target / "index.html"
            assert target.is_file(), (path, href)


def test_the_workflow_publishes_site_only_with_pinned_actions():
    text = WORKFLOW.read_text(encoding="utf-8")
    uses = re.findall(r"uses:\s*(\S+)", text)
    assert uses and all(re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", u) for u in uses), uses
    assert re.search(r"path:\s*site\s*$", text, re.MULTILINE)
    assert "persist-credentials: false" in text
