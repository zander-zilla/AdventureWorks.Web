#!/usr/bin/env python3
"""C2-5 live eval (manual, after enable_ai is applied and 50_ai_reader.sql has run): asks the 30 eval questions through the
deployed app (real Bedrock model, guard, ai_reader user) and compares each answer with the reference query, which this script
runs itself through the Redshift Data API with your admin credentials. Uses the AWS CLI; costs a few cents of Bedrock tokens.

  python3 scripts/aws/ai-live-eval.py --url https://<after_url>/ --workgroup "$(terraform -chdir=infra/live output -raw redshift_workgroup)"

Each question counts against the demo login's daily budget (20 by default): run it with Ai__SessionQuestions raised, or in
two halves on two logins (--email). Exit code 0 when every answer matches.
"""
import argparse, http.cookiejar, json, os, subprocess, sys, time, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True); ap.add_argument("--workgroup", required=True); ap.add_argument("--database", default="aw_dw")
ap.add_argument("--email", default="ops@adventure-works.com"); ap.add_argument("--password", default=os.environ.get("AW_DEMO_PASSWORD", "Demo!2026"))
ap.add_argument("--only", default="", help="comma-separated question ids")
a = ap.parse_args()
base = a.url.rstrip("/") + "/api/v2"
jar = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def post(path, body):
    r = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                               headers={"Content-Type": "application/json", "X-AW-Client": "live-eval"})
    with jar.open(r, timeout=90) as resp: return json.loads(resp.read() or b"null")

def redshift(sql):
    sid = json.loads(subprocess.check_output(["aws", "redshift-data", "execute-statement", "--workgroup-name", a.workgroup,
                                              "--database", a.database, "--sql", sql]))["Id"]
    while True:
        d = json.loads(subprocess.check_output(["aws", "redshift-data", "describe-statement", "--id", sid]))
        if d["Status"] == "FINISHED": break
        if d["Status"] in ("FAILED", "ABORTED"): raise RuntimeError(d.get("Error"))
        time.sleep(1)
    res = json.loads(subprocess.check_output(["aws", "redshift-data", "get-statement-result", "--id", sid]))
    return [[None if f.get("isNull") else next(iter(f.values())) for f in rec] for rec in res["Records"]]

def norm(rows):
    out = []
    for r in rows:
        row = []
        for x in r:
            try: row.append(round(float(x), 2))
            except (TypeError, ValueError): row.append(x)
        out.append(row)
    return out

def close(got, exp):
    return len(got) == len(exp) and all(len(g) == len(e) and all(
        (abs(x - y) <= max(0.01, abs(y) * 1e-6)) if isinstance(x, float) and isinstance(y, float) else x == y for x, y in zip(g, e))
        for g, e in zip(got, exp))

qs = json.load(open(os.path.join(ROOT, "src/AdventureWorks.Web/Ai/eval.json")))["questions"]
if a.only: qs = [q for q in qs if str(q["id"]) in a.only.split(",")]
post("/auth/login", {"email": a.email, "password": a.password})
ok = 0; tokens = 0
for q in qs:
    r = post("/ai/ask", {"question": q["question"]}); tokens += r["inputTokens"] + r["outputTokens"]
    if r.get("blocked") or r.get("error"):
        print(f"FAIL {q['id']:>2} {q['question']}: {r.get('blocked') or r.get('error')}  sql={r.get('sql')}"); continue
    exp = norm(redshift(q["expected"])[:200]); got = norm(r["rows"])
    if close(got, exp): ok += 1; print(f"ok   {q['id']:>2} {q['question']}")
    else: print(f"FAIL {q['id']:>2} {q['question']}\n     sql={r['sql']}\n     got={got[:3]} expected={exp[:3]}")
print(f"\n{ok}/{len(qs)} answers match the reference queries; {tokens} model tokens used.")
sys.exit(0 if ok == len(qs) else 1)
