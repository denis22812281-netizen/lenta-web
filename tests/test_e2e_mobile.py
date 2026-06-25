"""Mobile e2e tests via Playwright.

Run locally (requires server on :8000):
    uvicorn main:app &
    pytest tests/test_e2e_mobile.py -v

Run against Railway:
    PLAYWRIGHT_BASE_URL=https://lenta-web-production.up.railway.app \\
    PLAYWRIGHT_PHONE=+79997303914 PLAYWRIGHT_PASSWORD=yourpass \\
    pytest tests/test_e2e_mobile.py -v
"""
import os

from playwright.sync_api import Page, expect

BASE_URL = os.getenv("PLAYWRIGHT_BASE_URL", "http://localhost:8000").rstrip("/")
PHONE    = os.getenv("PLAYWRIGHT_PHONE",    "+79997303914")
PASSWORD = os.getenv("PLAYWRIGHT_PASSWORD", "test1234")

MOBILE_VIEWPORT = {"width": 390, "height": 844}
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)


def _login(page: Page):
    page.goto(f"{BASE_URL}/login")
    page.fill('input[name="phone"]', PHONE)
    page.click('button[type="submit"]')
    page.fill('input[name="password"]', PASSWORD)
    page.click('button[type="submit"]')


def _mobile(page: Page):
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.set_extra_http_headers({"User-Agent": MOBILE_UA})


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_login_page_renders_on_mobile(page: Page):
    """Login page loads and phone field is visible on 390px viewport."""
    _mobile(page)
    page.goto(f"{BASE_URL}/login")
    expect(page.locator('input[name="phone"], input[type="tel"]')).to_be_visible()


def test_login_redirects_to_dashboard(page: Page):
    """Successful login redirects to dashboard (not back to /login)."""
    _mobile(page)
    _login(page)
    page.wait_for_url(lambda url: "/login" not in url, timeout=8000)
    assert "/login" not in page.url


def test_unauthenticated_redirect_to_login(page: Page):
    """Accessing /smr without auth redirects to login."""
    _mobile(page)
    page.goto(f"{BASE_URL}/smr")
    page.wait_for_url("**login**", timeout=5000)
    assert "login" in page.url


# ── Navigation ────────────────────────────────────────────────────────────────

def test_bottom_nav_visible_on_mobile(page: Page):
    """Bottom navigation bar is rendered after login on mobile."""
    _mobile(page)
    _login(page)
    page.wait_for_url(f"{BASE_URL}/", timeout=8000)
    bottom_nav = page.locator(".bottom-nav, nav.bottom-nav")
    expect(bottom_nav).to_be_visible()


def test_no_horizontal_overflow_on_dashboard(page: Page):
    """Dashboard must not exceed viewport width on 390px — no horizontal scroll."""
    _mobile(page)
    _login(page)
    page.wait_for_url(f"{BASE_URL}/", timeout=8000)
    page.wait_for_load_state("networkidle")
    scroll_w = page.evaluate("document.body.scrollWidth")
    client_w = page.evaluate("document.documentElement.clientWidth")
    assert scroll_w <= client_w + 4, (
        f"Horizontal overflow: body.scrollWidth={scroll_w}px > clientWidth={client_w}px"
    )


# ── SMR page ──────────────────────────────────────────────────────────────────

def test_smr_list_loads_without_error(page: Page):
    """SMR list page loads without JS errors on mobile (was crashing on iOS)."""
    _mobile(page)
    js_errors = []
    page.on("pageerror", lambda e: js_errors.append(str(e)))
    _login(page)
    page.goto(f"{BASE_URL}/smr", wait_until="networkidle")
    assert page.locator("h1, .page-title, .smr-section-title, h5").count() > 0, \
        "SMR page has no headings — may not have loaded"
    assert not js_errors, f"JS errors on /smr: {js_errors}"


def test_smr_list_no_horizontal_overflow(page: Page):
    """SMR list must not overflow horizontally on 390px."""
    _mobile(page)
    _login(page)
    page.goto(f"{BASE_URL}/smr", wait_until="networkidle")
    scroll_w = page.evaluate("document.body.scrollWidth")
    client_w = page.evaluate("document.documentElement.clientWidth")
    assert scroll_w <= client_w + 4, \
        f"Horizontal overflow on /smr: {scroll_w}px > {client_w}px"


# ── CSP compliance ────────────────────────────────────────────────────────────

def test_no_csp_violations_on_dashboard(page: Page):
    """No Content-Security-Policy violations on dashboard (no unsafe-inline blocked scripts)."""
    _mobile(page)
    csp_violations = []
    page.on("console", lambda msg: csp_violations.append(msg.text)
            if "Content Security Policy" in msg.text or "refused to execute" in msg.text.lower()
            else None)
    _login(page)
    page.wait_for_url(f"{BASE_URL}/", timeout=8000)
    page.wait_for_load_state("networkidle")
    assert not csp_violations, f"CSP violations: {csp_violations}"


def test_no_csp_violations_on_smr(page: Page):
    """No CSP violations on /smr page."""
    _mobile(page)
    csp_violations = []
    page.on("console", lambda msg: csp_violations.append(msg.text)
            if "Content Security Policy" in msg.text or "refused to execute" in msg.text.lower()
            else None)
    _login(page)
    page.goto(f"{BASE_URL}/smr", wait_until="networkidle")
    assert not csp_violations, f"CSP violations on /smr: {csp_violations}"


# ── Key pages load ────────────────────────────────────────────────────────────

def test_vpk_page_loads(page: Page):
    """VPK page loads and renders content on mobile."""
    _mobile(page)
    _login(page)
    page.goto(f"{BASE_URL}/vpk", wait_until="networkidle")
    assert page.title() != "", "Page has no title"
    assert page.locator("body").inner_text() != "", "Page body is empty"


def test_vpk_cta_touch_target(page: Page):
    """VPK create button meets 36px minimum touch target height."""
    _mobile(page)
    _login(page)
    page.goto(f"{BASE_URL}/vpk")
    page.wait_for_load_state("networkidle")
    cta = page.locator(
        "a[href*='/vpk/new'], a[href*='/vpk/create'], "
        "button:has-text('Создать'), a:has-text('Создать')"
    )
    if cta.count() > 0:
        box = cta.first.bounding_box()
        assert box is not None, "CTA button has no bounding box"
        assert box["height"] >= 36, f"Touch target too small: {box['height']:.0f}px"


def test_chat_page_loads_and_input_visible(page: Page):
    """Chat page loads and input field is visible on mobile."""
    _mobile(page)
    _login(page)
    page.goto(f"{BASE_URL}/chat", wait_until="domcontentloaded")
    chat_input = page.locator("#chat-input-field, .chat-input, textarea[name='message']")
    expect(chat_input).to_be_visible(timeout=5000)


def test_managers_page_loads(page: Page):
    """Managers page loads on mobile."""
    _mobile(page)
    _login(page)
    page.goto(f"{BASE_URL}/managers", wait_until="networkidle")
    assert page.locator("body").inner_text() != ""


def test_projects_page_loads(page: Page):
    """Projects/dashboard page loads on mobile without horizontal overflow."""
    _mobile(page)
    _login(page)
    page.goto(f"{BASE_URL}/projects", wait_until="networkidle")
    scroll_w = page.evaluate("document.body.scrollWidth")
    client_w = page.evaluate("document.documentElement.clientWidth")
    assert scroll_w <= client_w + 4, \
        f"Horizontal overflow on /projects: {scroll_w}px > {client_w}px"


# ── Security headers ──────────────────────────────────────────────────────────

def test_security_headers_present(page: Page):
    """Key security headers are present in responses."""
    response = page.goto(f"{BASE_URL}/login")
    assert response is not None
    headers = response.headers
    assert "x-frame-options" in headers, "Missing X-Frame-Options"
    assert "x-content-type-options" in headers, "Missing X-Content-Type-Options"
    assert "content-security-policy" in headers, "Missing CSP header"
    csp = headers.get("content-security-policy", "")
    assert "'unsafe-inline'" not in csp, f"'unsafe-inline' still in CSP: {csp}"
    assert "nonce-" in csp, f"No nonce in CSP: {csp}"
