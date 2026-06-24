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

import pytest
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


def test_login_page_renders_on_mobile(page: Page):
    """Login page loads and phone field is visible on 390px viewport."""
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.set_extra_http_headers({"User-Agent": MOBILE_UA})
    page.goto(f"{BASE_URL}/login")
    phone_input = page.locator('input[name="phone"], input[type="tel"]')
    expect(phone_input).to_be_visible()


def test_bottom_nav_visible_on_mobile(page: Page):
    """Bottom navigation bar is rendered after login on mobile."""
    page.set_viewport_size(MOBILE_VIEWPORT)
    _login(page)
    page.wait_for_url(f"{BASE_URL}/", timeout=8000)
    bottom_nav = page.locator(".bottom-nav-mobile, #bottom-nav")
    expect(bottom_nav).to_be_visible()


def test_chat_input_stays_visible(page: Page):
    """Chat input field doesn't disappear when focused (keyboard-open simulation)."""
    page.set_viewport_size(MOBILE_VIEWPORT)
    _login(page)
    page.goto(f"{BASE_URL}/chat")
    chat_input = page.locator(
        ".chat-input, input[name='message'], textarea[name='message']"
    )
    expect(chat_input).to_be_visible(timeout=5000)
    chat_input.scroll_into_view_if_needed()
    expect(chat_input).to_be_visible()


def test_vpk_cta_touch_target(page: Page):
    """VPK create button meets 36px minimum touch target height (Apple HIG: 44px)."""
    page.set_viewport_size(MOBILE_VIEWPORT)
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
        assert box["height"] >= 36, f"Touch target too small: {box['height']:.0f}px (min 36px)"


def test_no_horizontal_overflow_on_dashboard(page: Page):
    """Dashboard must not exceed viewport width on 390px — no horizontal scroll."""
    page.set_viewport_size(MOBILE_VIEWPORT)
    _login(page)
    page.wait_for_url(f"{BASE_URL}/", timeout=8000)
    page.wait_for_load_state("networkidle")
    scroll_w = page.evaluate("document.body.scrollWidth")
    client_w = page.evaluate("document.documentElement.clientWidth")
    assert scroll_w <= client_w + 4, (
        f"Horizontal overflow detected: body.scrollWidth={scroll_w}px "
        f"> clientWidth={client_w}px"
    )
