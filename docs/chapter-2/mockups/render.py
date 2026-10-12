"""Static HTML mockups for the Chapter 2 visual directions (no build, no network).
python docs/chapter-2/mockups/render.py && google-chrome --headless ... (see README in PLAN.md)"""
import pathlib
D = pathlib.Path(__file__).parent
DIRS = {
 "a-trail": dict(name="A · Trail (warm outdoor, light)", bg="#f7f4ee", panel="#ffffff", ink="#1f2a24", mute="#6b7468",
   accent="#2f6b4f", accent2="#d98c3a", line="#e6e0d4", font="'Georgia', serif", body="system-ui, sans-serif", radius="14px"),
 "b-console": dict(name="B · Ops console (dark, data-dense)", bg="#0f1420", panel="#171e2e", ink="#e6ebf5", mute="#8a94a8",
   accent="#6c7cff", accent2="#2dd4bf", line="#263049", font="'Inter', system-ui, sans-serif", body="system-ui, sans-serif", radius="8px"),
 "c-editorial": dict(name="C · Editorial retail (bold, high-contrast)", bg="#ffffff", panel="#f4f4f4", ink="#111111", mute="#666666",
   accent="#111111", accent2="#ff5a1f", line="#e2e2e2", font="'Helvetica Neue', Arial, sans-serif", body="'Helvetica Neue', Arial, sans-serif", radius="0px"),
}
ORDERS = [("SO-DDB-0142","Catherine Abel","2026-10-12","In process","$2,443.35"),("SO-DDB-0141","Kim Abercrombie","2026-10-12","Approved","$564.99"),
 ("SO-DDB-0139","Humberto Acevedo","2026-10-11","Backordered","$1,120.00"),("SO-DDB-0137","Pilar Ackerman","2026-10-11","Shipped","$89.98"),
 ("SO-DDB-0133","Frances Adams","2026-10-10","Cancelled","$34.99")]
def page(k, t):
    st = {"In process":t["accent2"],"Approved":t["accent"],"Backordered":"#c2410c","Shipped":"#15803d","Cancelled":t["mute"]}
    rows = "".join(f"<tr><td class=m>{o}</td><td>{c}</td><td>{d}</td><td><span class=pill style='border-color:{st[s]};color:{st[s]}'>{s}</span></td><td class=r>{v}</td></tr>" for o,c,d,s,v in ORDERS)
    kpi = "".join(f"<div class=card><div class=lbl>{a}</div><div class=big>{b}</div><div class=lbl>{c}</div></div>" for a,b,c in
      [("Orders to ship","37","SAL-05 · ORDERSTATUS GSI"),("Below reorder point","12","INV-02 · sparse index"),("Open POs","8","PUR-07"),("Open work orders","64","INV-06")])
    return f"""<!doctype html><meta charset=utf-8><title>{t['name']}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:{t['bg']};color:{t['ink']};font:14px/1.45 {t['body']}}}
header{{display:flex;align-items:center;gap:24px;padding:14px 28px;border-bottom:1px solid {t['line']};background:{t['panel']}}}
.logo{{font:700 19px {t['font']}}}.logo b{{color:{t['accent2']}}}
.sw{{display:flex;border:1px solid {t['line']};border-radius:999px;padding:3px;margin-left:auto}}.sw span{{padding:6px 14px;border-radius:999px;color:{t['mute']}}}
.sw .on{{background:{t['accent']};color:#fff}}nav a{{margin-right:18px;color:{t['mute']};text-decoration:none}}nav a.on{{color:{t['ink']};font-weight:600;border-bottom:2px solid {t['accent2']};padding-bottom:4px}}
main{{display:grid;grid-template-columns:220px 1fr;min-height:620px}}aside{{border-right:1px solid {t['line']};padding:20px}}aside div{{padding:8px 12px;border-radius:{t['radius']};margin-bottom:4px;color:{t['mute']}}}aside .on{{background:{t['panel']};color:{t['ink']};font-weight:600;border:1px solid {t['line']}}}
section{{padding:24px 32px}}h1{{font:700 28px {t['font']};margin:0 0 4px}}.sub{{color:{t['mute']};margin-bottom:20px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}}.card{{background:{t['panel']};border:1px solid {t['line']};border-radius:{t['radius']};padding:14px 16px}}
.lbl{{color:{t['mute']};font-size:12px}}.big{{font:700 30px {t['font']}}}
table{{width:100%;border-collapse:collapse;background:{t['panel']};border:1px solid {t['line']};border-radius:{t['radius']};overflow:hidden}}th,td{{text-align:left;padding:11px 14px;border-bottom:1px solid {t['line']}}}th{{color:{t['mute']};font-size:12px;text-transform:uppercase;letter-spacing:.05em}}
.m{{font-family:ui-monospace,monospace}}.r{{text-align:right}}.pill{{border:1px solid;border-radius:999px;padding:2px 10px;font-size:12px}}
.btn{{background:{t['accent']};color:#fff;border:0;border-radius:{t['radius']};padding:9px 16px;font-weight:600;float:right}}.btn2{{background:transparent;color:{t['ink']};border:1px solid {t['line']};margin-right:8px}}
.tag{{position:fixed;bottom:12px;right:16px;color:{t['mute']};font-size:12px}}</style>
<header><div class=logo>Adventure<b>Works</b></div><nav><a>Story</a><a>Architecture</a><a>Data</a><a class=on>Back office</a><a>Shop</a><a>Analytics</a></nav>
<div class=sw><span>Chapter 1 · Migration</span><span class=on>Chapter 2 · Extend &amp; modernize</span></div></header>
<main><aside><div class=on>Orders</div><div>Procurement</div><div>Production floor</div><div>Catalog &amp; pricing</div><div>Reviews</div><div>Ask the data ✦</div></aside>
<section><button class=btn>Ship selected</button><button class="btn btn2">Cancel</button><h1>Order fulfilment</h1><div class=sub>Orders placed in the new shop, approve → pick → ship. One click = TransactWriteItems (status + stock + TransactionHistory), then CDC and zero-ETL.</div>
<div class=kpis>{kpi}</div><table><tr><th>Order</th><th>Customer</th><th>Date</th><th>Status</th><th class=r>Total</th></tr>{rows}</table></section></main>
<div class=tag>Mockup · direction {t['name']}</div>"""
for k, t in DIRS.items():
    (D / f"{k}.html").write_text(page(k, t))
    print(k)
