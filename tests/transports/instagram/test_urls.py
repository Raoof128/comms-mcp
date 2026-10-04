"""Proposed A49, plan IG-4: a publish URL is checked, never fetched (section 6; D-I6)."""

import pytest

from comms.transports.instagram.urls import URL_MAX, public_url

GOOD = (
    "https://cdn.example.com/a/b.jpg",
    "https://cdn.example.com:443/a.jpg?sig=abc&x=1",
    "https://xn--bcher-kva.example/reel.mp4",
    "https://a-b.example.co.uk/p",
)


@pytest.mark.parametrize("url", GOOD)
def test_a_public_https_url_passes_unchanged(url):
    assert public_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://cdn.example.com/a.jpg",  # not https
        "ftp://cdn.example.com/a.jpg",
        "https://user:pw@cdn.example.com/a.jpg",  # userinfo
        "https://user@cdn.example.com/a.jpg",
        "https://127.0.0.1/a.jpg",  # IP literals, every spelling
        "https://[::1]/a.jpg",
        "https://2130706433/a.jpg",
        "https://0x7f.0.0.1/a.jpg",
        "https://10.1/a.jpg",
        "https://localhost/a.jpg",
        "https://img.localhost/a.jpg",
        "https://printer.local/a.jpg",
        "https://db.internal/a.jpg",
        "https://router.home.arpa/a.jpg",
        "https://intranet/a.jpg",  # a single label is not a public DNS name
        "https://cdn.example.com:8443/a.jpg",  # only the https port
        "https://-bad.example.com/a.jpg",
        "https://bad-.example.com/a.jpg",
        "https://cdn.exa mple.com/a.jpg",
        "https://cdn.example.com/a b.jpg",
        "https://cdn.example.com/a\n.jpg",
        "https://bücher.example/a.jpg",  # IDNs travel as punycode
        "https://cdn.example.123/a.jpg",  # a numeric TLD
        "https:///a.jpg",
        "https://cdn.example.com/" + "a" * URL_MAX,  # length
        "",
        None,
        42,
    ],
)
def test_anything_else_is_refused(url):
    with pytest.raises(ValueError):
        public_url(url)


def test_the_limit_is_2048_characters():
    base = "https://cdn.example.com/"
    assert URL_MAX == 2048
    assert public_url(base + "a" * (URL_MAX - len(base))) is not None
    with pytest.raises(ValueError):
        public_url(base + "a" * (URL_MAX - len(base) + 1))
