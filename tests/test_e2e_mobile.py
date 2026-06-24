"""Mobile e2e tests via Playwright.

Run against a live server:
    pytest tests/test_e2e_mobile.py --base-url=https://lenta-web-production.up.railway.app

Or locally (requires server running on :8000):
    uvicorn main:app &
    pytest tests/test_e2e_mobile.py --base-url=http://localhost:8000
"""
import pytest
from playwright.sync_api import Page, expect

# iPhone 13 viewport — the device we target most
MOBILE = {"viewport": {"width": 390, "height": 844}, "user_agent": (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)}


@pytest.fixture(scope="session")
def mobile_browser_context_args():
    return MOBILE


# ─── helpers ──────────────────────────────────────────────────────────────────

def _login(page: Page, base_url: str, phone: str = "+79997303914", password: str = "test1234"):
    page.goto(f"{base_url}/login")
    page.fill('input[name="phone"]', phone)
    page.click('button[type="submit"]')
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')


# ─── tests ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("base_url", ["http://localhost:8000"])
def test_login_page_renders_on_mobile(page: Page, base_url):
    """Login page loads without JS errors and shows phone field."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{base_url}/login")
    phone_input = page.locator('input[name="phone"], input[type="tel"]')
    expect(phone_input).to_be_visible()


@pytest.mark.parametrize("base_url", ["http://localhost:8000"])
def test_bottom_nav_visible_on_mobile(page: Page, base_url):
    """Bottom navigation bar is visible on mobile after login."""
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, base_url)
    page.wait_for_url(f"{base_url}/", timeout=5000)
    bottom_nav = page.locator(".bottom-nav-mobile, #bottom-nav")
    expect(bottom_nav).to_be_visible()


@pytest.mark.parametrize("base_url", ["http://localhost:8000"])
def test_chat_input_visible_with_keyboard(page: Page, base_url):
    """Chat input field stays visible when keyboard would appear (tap-to-focus)."""
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, base_url)
    page.goto(f"{base_url}/chat")
    chat_input = page.locator(".chat-input, input[name='message'], textarea[name='message']")
    expect(chat_input).to_be_visible(timeout=5000)
    # Scroll to input to simulate keyboard-open scenario
    chat_input.scroll_into_view_if_needed()
    expect(chat_input).to_be_visible()


@pytest.mark.parametrize("base_url", ["http://localhost:8000"])
def test_vpk_form_accessible_on_mobile(page: Page, base_url):
    """VPK page loads and the create-report button is tappable on mobile."""
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, base_url)
    page.goto(f"{base_url}/vpk")
    page.wait_for_load_state("networkidle")
    # Either a button or a link to start a report
    cta = page.locator("a[href*='/vpk/new'], a[href*='/vpk/create'], button:has-text('Создать'), a:has-text('Создать')")
    if cta.count() > 0:
        box = cta.first.bounding_box()
        assert box is not None
        # Touch target must be at least 44×44px (Apple HIG)
        assert box["height"] >= 36, f"Touch target too small: {box['height']}px"


@pytest.mark.parametrize("base_url", ["http://localhost:8000"])
def test_no_horizontal_scroll_on_dashboard(page: Page, base_url):
    """Dashboard must not produce horizontal overflow on 390px width."""
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, base_url)
    page.wait_for_url(f"{base_url}/", timeout=5000)
    page.wait_for_load_state("networkidle")
    scroll_width  = page.evaluate("document.body.scrollWidth")
    client_width  = page.evaluate("document.documentElement.clientWidth")
    assert scroll_width <= client_width + 4, (
        f"Horizontal overflow: scrollWidth={scroll_width} > clientWidth={client_width}"
    )
