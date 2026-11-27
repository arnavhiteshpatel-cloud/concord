"""The sponsor evidence portal is served as static files at /portal (before the "/" web mount)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from neurometric.api.app import DEFAULT_PORTAL, create_app


def _client(tmp_path):
    return TestClient(create_app(tmp_path / "nm.sqlite", backup_dir=tmp_path / "backups"))


def test_portal_index_served(tmp_path):
    c = _client(tmp_path)
    r = c.get("/portal/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "NeuroMetric" in body and 'id="demo-banner"' in body
    assert "DEMO — synthetic data, not patients" in body
    assert 'src="js/app.js"' in body
    # hardened headers apply to the portal too (no inline scripts, same-origin only)
    assert "script-src 'self'" in r.headers["content-security-policy"]


def test_portal_redirect_and_assets(tmp_path):
    c = _client(tmp_path)
    r = c.get("/portal", follow_redirects=False)
    assert r.status_code in (301, 302, 307, 308)
    assert r.headers["location"].endswith("/portal/")
    js = c.get("/portal/js/app.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
    css = c.get("/portal/css/portal.css")
    assert css.status_code == 200 and "text/css" in css.headers["content-type"]


def test_portal_does_not_shadow_api(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/health").json()["status"] == "ok"
    assert c.get("/portal/does-not-exist.js").status_code == 404


def test_portal_is_self_contained():
    """No external (CDN) scripts, styles or fonts anywhere in the portal (CSP + COEP)."""
    for p in DEFAULT_PORTAL.rglob("*"):
        if p.suffix in {".html", ".js", ".css"}:
            text = p.read_text("utf-8").replace("http://www.w3.org/2000/svg", "")
            assert "http://" not in text and "https://" not in text, p
            assert "innerHTML" not in text, p
