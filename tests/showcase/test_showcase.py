"""Phase 8 showcase: Playwright tests of every tab against the static build (no AWS, no app/CDC stack needed).

Builds showcase/dist into a temp dir with a stub app page, serves it, and walks each tab.
SHOWCASE_SCREENSHOTS=<dir> saves one full-page screenshot per tab (used for the PR); SHOWCASE_APP_URL embeds a real app.
"""
import functools, json, os, sys, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

import pytest
from playwright.sync_api import sync_playwright, expect

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "showcase"))
import build  # noqa: E402

SHOTS = os.environ.get("SHOWCASE_SCREENSHOTS")
LIVE = os.environ.get("SHOWCASE_LIVE") == "1"
M = json.load(open(os.path.join(ROOT, "design", "mapping", "mapping.json")))
AP = json.load(open(os.path.join(ROOT, "docs", "design", "access-patterns.json")))


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("showcase") / "dist")
    if os.environ.get("SHOWCASE_URL"):  # an already running scripts/showcase-up.sh (live mode)
        yield os.environ["SHOWCASE_URL"].rstrip("/") + "/"
        return
    build.build(out, app_url=os.environ.get("SHOWCASE_APP_URL", "stub-app.html"),
                before_url=os.environ.get("SHOWCASE_BEFORE_URL", "stub-before.html"))
    with open(os.path.join(out, "stub-app.html"), "w") as f:
        f.write("<h1 id='stub'>AdventureWorks After app (stub)</h1>")
    with open(os.path.join(out, "stub-before.html"), "w") as f:
        f.write("<h1 id='stub'>AdventureWorks Before app (stub)</h1>")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(SimpleHTTPRequestHandler, directory=out))
    srv.RequestHandlerClass.log_message = lambda *a: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/" % srv.server_address[1]
    srv.shutdown()


@pytest.fixture(scope="module")
def page(base):
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1366, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base)
        yield pg
        b.close()
        assert not errors, errors


def tab(page, name, shot):
    page.get_by_role("tab", name=name).click()
    page.wait_for_timeout(300)
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=os.path.join(SHOTS, shot), full_page=True)


def test_presentation(page):
    expect(page.locator("#slide h3")).to_contain_text("modernized")
    page.locator("#next").click()
    page.locator("#next").click()
    expect(page.locator("#slide")).to_contain_text("DynamoDB items")
    expect(page.locator("#slide .kpi").nth(1)).to_contain_text("815,361")
    tab(page, "Presentation", "1-presentation.png")


def test_before_architecture(page):
    page.get_by_role("tab", name="Before Architecture").click()
    sec = page.locator("#archbefore")
    expect(sec.locator(".node")).to_have_count(7)
    sec.locator('.node[data-id="ef"]').click()
    expect(sec.locator(".archd")).to_contain_text("Entity Framework Core 2.1")
    sec.locator('.node[data-id="dw"]').click()
    expect(sec.locator(".archd")).to_contain_text("AdventureWorksDW2022")
    tab(page, "Before Architecture", "2a-before-architecture.png")


def test_after_architecture(page):
    page.get_by_role("tab", name="After Architecture").click()
    sec = page.locator("#archafter")
    expect(sec.locator(".node")).to_have_count(13)
    sec.locator('.node[data-id="cicd"]').click()
    expect(sec.locator(".archd")).to_contain_text("OIDC")
    sec.locator('.node[data-id="lambda"]').click()
    expect(sec.locator(".archd")).to_contain_text("awcdc")
    tab(page, "After Architecture", "2b-after-architecture.png")


def test_data_mapping(page):
    page.get_by_role("tab", name="Data Mapping").click()
    n = sum(len({i["table"] for i in v.get("items") or []}) for v in M["sources"].values())  # listed under each target table
    expect(page.locator("#mlist .i")).to_have_count(n)
    expect(page.locator("#mdetail")).to_contain_text("ORDER#{SalesOrderID:010d}")
    page.fill("#msearch", "Person.Person")
    page.locator("#mlist .i", has_text="Person.Person").first.click()
    expect(page.locator("#mdetail")).to_contain_text("BE#{BusinessEntityID:06d}")
    page.fill("#msearch", "")
    page.locator('#mlist .i[data-s="Sales.SalesOrderHeader"]').click()
    tab(page, "Data Mapping", "3a-data-mapping-dynamodb.png")
    page.get_by_role("button", name="DynamoDB → Redshift star schema").click()
    expect(page.locator("#dlist .i")).to_have_count(len(M["dw_lineage"]))
    expect(page.locator("#ddetail")).to_contain_text("dw.fact_internet_sales")
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, "3b-data-mapping-redshift.png"), full_page=True)


def test_access_patterns(page):
    page.get_by_role("tab", name="Access Patterns").click()
    expect(page.locator("#prows tr")).to_have_count(len(AP["patterns"]))
    page.select_option("#pscope", "dynamodb")
    expect(page.locator("#prows tr")).to_have_count(sum(p["scope"] == "dynamodb" for p in AP["patterns"]))
    expect(page.locator('#prows tr[data-id="CAT-01"]')).to_contain_text("Query PK = 'CATALOG'")
    page.select_option("#pdom", "Sales")
    tab(page, "Access Patterns", "4-access-patterns.png")


def test_live_replication(page):
    page.get_by_role("tab", name="Live Replication").click()
    fr = page.frame_locator("#monitor")
    if LIVE:
        expect(fr.locator("#rows tr.c").first).to_be_visible(timeout=30000)
    else:
        expect(fr.locator("#rows tr.c")).to_have_count(3)
        fr.locator("#rows tr.c").last.click()
        expect(fr.locator("pre").nth(1)).to_contain_text("ORDER#0000075124")
    tab(page, "Live Replication", "5a-live-replication.png")
    page.get_by_role("button", name="Side by side with the Before App").click()
    expect(page.locator("#beforeside")).to_be_visible()
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, "5b-live-replication-side-by-side.png"), full_page=True)


def test_before_app(page):
    page.get_by_role("tab", name="Before App").click()
    expect(page.locator("#beforeframe")).to_be_visible()
    expect(page.locator("#before")).to_contain_text("catherine0@adventure-works.com")
    if not os.environ.get("SHOWCASE_BEFORE_URL"):
        expect(page.frame_locator("#beforeframe").locator("#stub")).to_contain_text("Before")
    tab(page, "Before App", "6-before-app.png")


def test_after_app(page):
    page.get_by_role("tab", name="After App").click()
    expect(page.locator("#appframe")).to_be_visible()
    if not os.environ.get("SHOWCASE_APP_URL"):
        expect(page.frame_locator("#appframe").locator("#stub")).to_be_visible()
    else:
        page.wait_for_timeout(2500)
    tab(page, "After App", "7-after-app.png")


@pytest.mark.skipif(not LIVE, reason="SHOWCASE_LIVE=1 with scripts/cdc-up.sh + before app running")
def test_write_in_before_app_shows_in_live_replication(page):
    """Demo flow: order in the Before App frame (SQL Server) -> monitor shows it applied to DynamoDB."""
    page.get_by_role("tab", name="Live Replication").click()
    page.get_by_role("button", name="Side by side with the Before App").click()
    bf = page.frame_locator("#beforeside")
    page.locator("#beforeside").evaluate("f => f.src = new URL('/Account/Login', f.src).href")
    bf.locator('input[name="email"]').fill("catherine0@adventure-works.com")
    bf.locator('input[name="password"]').fill("Demo!2026")
    bf.get_by_role("button", name="Log in").click()
    page.locator("#beforeside").evaluate("f => f.src = new URL('/Shop', f.src).href")
    bf.get_by_role("button", name="Order").first.click()
    expect(bf.locator("body")).to_contain_text("SO", timeout=15000)
    mon = page.frame_locator("#monitor")
    expect(mon.locator("#rows tr.c", has_text="Sales.SalesOrderHeader").first).to_be_visible(timeout=60000)
    mon.locator("#rows tr.c", has_text="Sales.SalesOrderHeader").first.click()
    expect(mon.locator("pre").nth(1)).to_contain_text("ORDER#", timeout=10000)
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, "5c-live-replication-before-app-write.png"), full_page=True)


def test_deep_link(page, base):
    page.goto(base + "#patterns")
    expect(page.locator("#patterns")).to_be_visible()
