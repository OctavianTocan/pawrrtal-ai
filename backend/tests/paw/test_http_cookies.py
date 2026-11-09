"""Cookie jar must round-trip Set-Cookie values containing commas (Expires=...,GMT).

Regression guard for the choice to use ``http.cookiejar.MozillaCookieJar`` over a
hand-rolled Set-Cookie parser: dates like ``Wed, 27-May-2099 12:00:00 GMT``
contain commas that naive split-by-comma parsers tokenise incorrectly.
"""

from __future__ import annotations

import http.cookiejar
from pathlib import Path

from app.cli.paw.http import load_cookies, save_cookies

# 2100-01-01 00:00 UTC; ensures a real Expires=...,GMT field is serialised.
FUTURE_EXPIRES_EPOCH = 4102444800
EXPECTED_COOKIE_FILE_MODE = 0o600


def test_cookie_with_expires_comma_roundtrips(tmp_path: Path) -> None:
    """Save+load a cookie whose Expires contains a comma; values must survive."""
    path = tmp_path / "cookies.txt"
    jar = http.cookiejar.MozillaCookieJar(str(path))
    cookie = http.cookiejar.Cookie(
        version=0,
        name="session_token",
        value="abc123",
        port=None,
        port_specified=False,
        domain="127.0.0.1",
        domain_specified=True,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=False,
        expires=FUTURE_EXPIRES_EPOCH,
        discard=False,
        comment=None,
        comment_url=None,
        rest={"HttpOnly": ""},
        rfc2109=False,
    )
    jar.set_cookie(cookie)
    save_cookies(jar, path)

    loaded = load_cookies(path)
    cookies = list(loaded)
    assert len(cookies) == 1
    assert cookies[0].name == "session_token"
    assert cookies[0].value == "abc123"

    mode = path.stat().st_mode & 0o777
    assert mode == EXPECTED_COOKIE_FILE_MODE
