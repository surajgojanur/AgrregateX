"""Headless-browser QA for the AggregateX UI (Playwright + Chromium). Asserts as well as screenshots.

usage: python ui_qa.py <base_url> <out_dir> [full|outage]
  full   : landing (dark + light), /login redirect, anonymous secure-mode /app, tenant dashboard
           (KPIs, freshness badge, shard label, chart, Top-10, operator pages hidden, forced #/engine
           refused), operator Shards / Engine (B-3 table) / Monitoring, tenant switch, live write.
  outage : run WHILE shard A is partitioned: dashboard banner for a shard-A tenant, shard-B tenant
           still served, Shards page PARTIAL.
Fails (exit 1) on any assertion or any uncaught page error / console error (except expected HTTP
4xx/5xx resource logs, which the assertions cover explicitly).
"""
import json
import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE, OUT, MODE = sys.argv[1].rstrip("/"), sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "full")
results, errors = [], []


def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
        print("PASS", name, flush=True)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).splitlines()[0][:220]
        results.append((name, False, msg))
        print("FAIL", name, "-", msg, flush=True)


def watch(page, label):
    page.on("pageerror", lambda e: errors.append(f"{label}: pageerror {e}"))
    page.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text
            and errors.append(f"{label}: console {m.text[:200]}"))


def new_page(browser, label, theme="dark", login=None, width=1440):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    ctx.add_init_script(f"try{{localStorage.setItem('aggregatex.theme','{theme}')}}catch(e){{}}")
    page = ctx.new_page()
    watch(page, label)
    if login:
        r = page.request.post(f"{BASE}/api/auth/login", data=json.dumps({"email": login, "password": "demo1234"}),
                              headers={"content-type": "application/json"})
        assert r.status == 200, f"login {login} -> {r.status}"
    return page


def shot(page, name):
    page.screenshot(path=f"{OUT}/{name}.png", full_page=False)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    if MODE == "full":
        for theme in ("dark", "light"):
            p = new_page(browser, f"landing-{theme}", theme)
            p.goto(BASE + "/", wait_until="networkidle")

            def landing(p=p, theme=theme):
                expect(p).to_have_title(re.compile("AggregateX"))
                expect(p.locator("h1")).to_contain_text("tenant-isolated analytics")
                for sec in ("#problem", "#requirements", "#architecture", "#targets"):
                    expect(p.locator(sec)).to_be_visible()
                assert p.locator("svg.logo-mark").count() >= 1, "logo mark missing"
                assert p.locator("[aria-label^='Switch to'] svg").count() >= 1, "theme toggle icon missing"
                assert p.evaluate("document.documentElement.dataset.theme") == theme
                assert p.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "horizontal overflow"
            check(f"landing renders ({theme})", landing)
            shot(p, f"01-landing-{theme}")
        p = new_page(browser, "landing-mobile", width=390)
        p.goto(BASE + "/", wait_until="networkidle")
        check("landing mobile 390px: no horizontal overflow",
              lambda: (_ for _ in ()).throw(AssertionError("overflow")) if not p.evaluate(
                  "document.documentElement.scrollWidth <= window.innerWidth + 1") else None)
        shot(p, "02-landing-mobile")

        p = new_page(browser, "theme-toggle")
        p.goto(BASE + "/", wait_until="networkidle")

        def toggle(p=p):
            p.locator("[aria-label='Switch to light theme']").first.click()
            assert p.evaluate("document.documentElement.dataset.theme") == "light"
        check("theme toggle switches dark -> light", toggle)

        p = new_page(browser, "login-redirect")
        p.goto(BASE + "/login", wait_until="networkidle")
        check("/login redirects to landing (PR #26)", lambda: expect(p).to_have_url(re.compile(r"/(#.*)?$")))

        p = new_page(browser, "anon-app")
        p.goto(BASE + "/app#/dashboard", wait_until="networkidle")

        def anon():
            expect(p.get_by_text(re.compile("restricted|sign", re.I)).first).to_be_visible(timeout=10000)
            assert "/app" in p.url, f"redirect loop / left /app: {p.url}"
        check("secure mode: anonymous /app shows restricted access, no loop", anon)
        shot(p, "03-anonymous-secure-mode")

        # tenant session
        p = new_page(browser, "tenant2", login="tenant2@demo.local")
        p.goto(BASE + "/app#/dashboard", wait_until="networkidle")

        def tenant_dash():
            expect(p.locator(".stat__value").first).not_to_have_text("—", timeout=15000)
            expect(p.locator(".ax-fresh")).to_contain_text(re.compile(r"Updated \d+"), timeout=15000)
            expect(p.locator(".ax-shardline")).to_contain_text("shard B")
            assert p.locator("path.ax-line").count() == 1, "trend line missing"
            rows = p.locator("section:has-text('Top 10 products') tbody tr").count()
            assert 1 <= rows <= 10, f"top-10 rows={rows}"
            nav = p.locator(".sidebar__nav").inner_text().lower()   # labels are CSS-uppercased
            for hidden in ("Shards", "Engine", "Monitoring"):
                assert hidden.lower() not in nav, f"tenant sees {hidden}"
        check("tenant dashboard: KPIs, freshness badge, shard B, chart, Top-10, operator nav hidden", tenant_dash)
        shot(p, "04-tenant2-dashboard")
        p.goto(BASE + "/app#/engine", wait_until="networkidle")
        check("tenant forced #/engine is refused (stays on dashboard)",
              lambda: expect(p.locator(".ax-shardline")).to_be_visible(timeout=10000))

        # operator session
        p = new_page(browser, "operator", login="admin@demo.local")
        p.goto(BASE + "/app#/dashboard", wait_until="networkidle")

        def op_nav():
            nav = p.locator(".sidebar__nav").inner_text().lower()   # labels are CSS-uppercased
            for shown in ("Shards", "Engine", "Monitoring"):
                assert shown.lower() in nav, f"operator lacks {shown}"
        check("operator nav shows Shards, Engine, Monitoring", op_nav)

        def switch():
            p.locator("select.select").select_option("5")
            expect(p.locator(".ax-shardline")).to_contain_text("Tenant 5 lives on shard B", timeout=10000)
            expect(p.locator(".stat__value").first).not_to_have_text("—", timeout=15000)
        check("operator switches tenant (5 -> shard B) and data loads", switch)

        def live_write():
            p.get_by_role("button", name=re.compile("Insert order")).click()
            expect(p.get_by_text(re.compile("Measured commit"))).to_be_visible(timeout=40000)
        check("live write: insert order -> measured commit-to-visible shown", live_write)
        shot(p, "05-operator-dashboard-livewrite")

        p.goto(BASE + "/app#/shards", wait_until="networkidle")

        def shards():
            expect(p.get_by_text("Shard A", exact=True)).to_be_visible(timeout=15000)
            expect(p.get_by_text("Shard B", exact=True)).to_be_visible()
            expect(p.get_by_text("all reachable")).to_be_visible()
        check("Shards page: both shards, complete", shards)
        shot(p, "06-shards")
        p.goto(BASE + "/app#/engine", wait_until="networkidle")

        def engine():
            expect(p.get_by_text("Per-tenant query limits (B-3)")).to_be_visible(timeout=15000)
            expect(p.get_by_text("st_day_product_status").first).to_be_visible()
        check("Engine page: stream tables + B-3 limits table", engine)
        shot(p, "07-engine")
        p.goto(BASE + "/app#/monitoring", wait_until="networkidle")

        def monitoring():
            p.wait_for_timeout(2500)
            body = p.locator("main").inner_text()
            assert len(body) > 50 and "Internal error" not in body, body[:200]
        check("Monitoring page (B-5) renders", monitoring)
        shot(p, "08-monitoring")
    else:  # outage
        p = new_page(browser, "outage", login="admin@demo.local")
        p.goto(BASE + "/app#/dashboard", wait_until="networkidle")

        def banner():
            p.locator("select.select").select_option("1")
            expect(p.locator(".ax-outage")).to_contain_text("Shard A unavailable", timeout=20000)
            expect(p.get_by_text(re.compile("No data shown rather than stale data")).first).to_be_visible()
        check("outage: shard-A tenant shows banner and no stale data", banner)
        shot(p, "09-outage-dashboard-tenant1")

        def b_ok():
            p.locator("select.select").select_option("2")
            expect(p.locator(".stat__value").first).not_to_have_text("—", timeout=15000)
            assert p.locator(".ax-outage").count() == 0
        check("outage: shard-B tenant still served", b_ok)
        p.goto(BASE + "/app#/shards", wait_until="networkidle")
        check("outage: Shards page shows PARTIAL",
              lambda: expect(p.get_by_text("PARTIAL total")).to_be_visible(timeout=20000))
        shot(p, "10-outage-shards")
    browser.close()

for e in errors:
    print("ERROR", e)
failed = [r for r in results if not r[1]]
print(json.dumps({"mode": MODE, "passed": len(results) - len(failed), "failed": len(failed), "js_errors": len(errors)}))
sys.exit(1 if failed or errors else 0)
