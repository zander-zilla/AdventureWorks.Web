"""Phase 5 Playwright smoke: login, browse, search, add to cart, checkout, order in history (after app + DynamoDB Local)."""
import os, re
import pytest
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get("AFTER_URL", "http://localhost:5090")


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        yield pg
        b.close()


def test_shopper_journey(page):
    page.goto(BASE + "/Account/Login")
    page.get_by_test_id("login-email").select_option("catherine0@adventure-works.com")
    page.get_by_test_id("login-password").fill("Demo!2026")
    page.get_by_test_id("login-submit").click()
    expect(page.get_by_test_id("user-name")).to_have_text("Catherine Abel")

    # browse: category -> subcategory -> product, culture switcher
    page.goto(BASE + "/classic")   # C2-2: / is the new UI; the Razor shop (Chapter 1) stays at /Shop and /classic
    page.get_by_test_id("subcategory-link").filter(has_text="Mountain Bikes").click()
    page.get_by_test_id("product-link").first.click()
    expect(page.get_by_test_id("product-name")).to_contain_text("Mountain")
    page.get_by_test_id("culture-fr").click()
    expect(page.get_by_test_id("product-description")).to_have_attribute("lang", "fr")
    page.get_by_test_id("add-to-cart").click()
    expect(page.get_by_test_id("cart-line")).to_have_count(1)

    # search (name prefix, D2)
    page.get_by_test_id("search-box").fill("touring-1000")
    page.get_by_test_id("search-go").click()
    page.get_by_test_id("search-result").first.click()
    page.get_by_test_id("add-to-cart").click()
    expect(page.get_by_test_id("cart-line")).to_have_count(2)

    # checkout (TransactWrite) -> order detail read strongly
    page.get_by_test_id("checkout").click()
    number = page.get_by_test_id("order-number").inner_text()
    assert re.fullmatch(r"SO-DDB-1\d{9}", number), number
    expect(page.get_by_test_id("order-line")).to_have_count(2)

    # cart is empty, order in history
    page.get_by_test_id("nav-cart").click()
    expect(page.get_by_test_id("cart-empty")).to_be_visible()
    page.get_by_test_id("nav-orders").click()
    expect(page.get_by_test_id("order-link").filter(has_text=number)).to_have_count(1)


def test_root_opens_the_new_ui(page):
    page.goto(BASE + "/")
    assert "/app/" in page.url, page.url
