"""After-app smoke (Playwright, real app image + DynamoDB Local). Phase 5 drove the Razor shop; C2-3 removed it (John's
C2-2 decision 3: Chapter 1 lives in tag v1.0-migration and at /c1/), so the same shopper journey now runs in the React
shop at /app/: login, browse, add to cart, checkout, order in history."""
import os, re
import urllib.request, urllib.error
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
    page.goto(BASE + "/app/login")
    page.get_by_label("Email").fill("catherine0@adventure-works.com")
    page.get_by_label("Password").fill("Demo!2026")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_test_id("user")).to_contain_text("Catherine")

    # browse: category tile -> subcategory -> product -> add to cart
    page.goto(BASE + "/app/shop/c/1")   # Mountain Bikes (CAT-03, GSI SUBCAT#)
    page.get_by_test_id("product-card").first.click()
    expect(page.get_by_test_id("list-price")).to_be_visible()
    page.get_by_test_id("add-to-cart").click()
    page.goto(BASE + "/app/shop/cart")
    expect(page.get_by_test_id("cart-line")).to_have_count(1)

    # checkout (TransactWrite) -> order page, then history
    expect(page.get_by_test_id("quote")).to_be_visible()
    page.get_by_test_id("place-order").click()
    heading = page.get_by_role("heading", level=1)
    expect(heading).to_have_text(re.compile(r"^SO-DDB-1\d{9}$"))
    number = heading.inner_text().strip()
    page.goto(BASE + "/app/shop/orders")
    expect(page.get_by_test_id("order-link").filter(has_text=number)).to_have_count(1)


def test_root_opens_the_new_ui(page):
    page.goto(BASE + "/")
    assert "/app/" in page.url, page.url


@pytest.mark.parametrize("path", ["/classic", "/Shop", "/Account/Login", "/Cart"])
def test_razor_ui_is_gone(path):
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(BASE + path)
    assert e.value.code == 404
