#!/usr/bin/env python3
"""Local CDC consumer: receives Debezium Server HTTP-sink events, queues them durably (SQLite), applies them in order
through the shared awcdc transform to DynamoDB (Local), and serves the replication monitor (API + static page).

Start PAUSED (default) so the bulk load can run while capture already buffers changes; POST /control/resume afterwards.
  POST /events            Debezium HTTP sink (single event or JSON array when batch mode is on)
  POST /control/pause|resume
  GET  /api/status        queue depth, applied, failed, last position, lag stats
  GET  /api/changes?limit=N   recent applied changes: SQL row -> DynamoDB items (+ lag)
  GET  /                  monitor page (cdc/monitor/index.html)
"""
import argparse, datetime, decimal, json, os, sqlite3, sys, threading, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts", "loader"))
from awcdc import transform as T  # noqa: E402
import ddb  # noqa: E402

MONITOR = os.path.join(HERE, "..", "monitor", "index.html")


def jdefault(o):
    if isinstance(o, decimal.Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    if isinstance(o, (bytes, bytearray)):
        return "0x" + bytes(o).hex()
    if isinstance(o, set):
        return sorted(o)
    return str(o)


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.lock = threading.Lock()
        self.db.executescript("""PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS inbox (id INTEGER PRIMARY KEY, body TEXT, received_ms INTEGER, state TEXT DEFAULT 'new', attempts INTEGER DEFAULT 0, error TEXT);
          CREATE TABLE IF NOT EXISTS changes (id INTEGER PRIMARY KEY, inbox_id INTEGER, tbl TEXT, op TEXT, position TEXT, commit_ms INTEGER,
                                              applied_ms INTEGER, lag_ms INTEGER, report TEXT);
          CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);""")

    def q(self, sql, args=()):
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def get(self, k, default=None):
        r = self.q("SELECT v FROM kv WHERE k=?", (k,)); return r[0][0] if r else default

    def set(self, k, v):
        self.q("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


class Applier(threading.Thread):
    def __init__(self, store, max_attempts=3):
        super().__init__(daemon=True)
        self.store, self.max_attempts = store, max_attempts
        self.mapping = T.load_json(T.default_mapping_path())
        sink = T.DynamoDBSink(ddb.resource())
        # same enrichment as the Lambda: event image + lookups of replicated items in DynamoDB (no SQL reads)
        self.rows = T.Enricher(self.mapping, sink)
        self.tr = T.Transformer(self.rows, sink, mapping=self.mapping)

    def run(self):
        while True:
            if self.store.get("paused", "1") == "1":
                time.sleep(0.5); continue
            nxt = self.store.q("SELECT id, body, attempts FROM inbox WHERE state='new' ORDER BY id LIMIT 1")
            if not nxt:
                time.sleep(0.2); continue
            iid, body, attempts = nxt[0]
            try:
                self.apply_one(iid, json.loads(body))
                self.store.q("UPDATE inbox SET state='done' WHERE id=?", (iid,))
            except Exception as e:  # retry in order (e.g. T.MissingParent: a referenced item not replicated yet, after the
                traceback.print_exc()  # Enricher's own bounded backoff); after max_attempts park it in the DLQ state and move on
                state = "dlq" if attempts + 1 >= self.max_attempts else "new"
                self.store.q("UPDATE inbox SET attempts=attempts+1, state=?, error=? WHERE id=?", (state, repr(e)[:2000], iid))
                time.sleep(1)

    def apply_one(self, iid, ev):
        p = ev.get("payload", ev) if isinstance(ev, dict) else None
        if not p or not p.get("op") or not (p.get("source") or {}).get("table"):
            return  # heartbeat / schema change / tombstone record
        ch = T.from_debezium(ev, self.rows.column_types)
        rep = self.tr.apply(ch)
        if rep.get("ignored"):
            return
        now = int(time.time() * 1000)
        lag = now - ch.commit_ts_ms if ch.commit_ts_ms else None
        report = {"row": rep["row"], "puts": rep["puts"], "tombstones": rep["tombstones"], "refreshed": rep["refreshed"],
                  "skipped": rep["skipped"], "pk": {c: (ch.after or ch.before or {}).get(c) for c in self.mapping["sources"][ch.table]["primary_key"]}}
        self.store.q("INSERT INTO changes(inbox_id,tbl,op,position,commit_ms,applied_ms,lag_ms,report) VALUES(?,?,?,?,?,?,?,?)",
                     (iid, ch.table, ch.op, ch.position, ch.commit_ts_ms, now, lag, json.dumps(report, default=jdefault)))
        self.store.set("last_position", ch.position)


def make_handler(store):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, obj=None, ctype="application/json", raw=None):
            body = raw if raw is not None else json.dumps(obj, default=jdefault).encode()
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body)

        def do_POST(self):
            if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
                # C2-7: large Debezium batches (e.g. a generated day) arrive chunked, without Content-Length
                data = b""
                while True:
                    size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                    if size == 0:
                        self.rfile.readline(); break
                    data += self.rfile.read(size); self.rfile.readline()
            else:
                n = int(self.headers.get("Content-Length") or 0); data = self.rfile.read(n) if n else b""
            path = urlparse(self.path).path
            if path == "/events":
                if not data.strip():
                    return self.send(200, {"ok": True})
                evs = json.loads(data)
                evs = evs if isinstance(evs, list) else [evs]
                now = int(time.time() * 1000)
                with store.lock:
                    store.db.execute("BEGIN")
                    for e in evs:
                        store.db.execute("INSERT INTO inbox(body, received_ms) VALUES(?,?)", (json.dumps(e), now))
                    store.db.execute("COMMIT")
                return self.send(200, {"queued": len(evs)})
            if path in ("/control/pause", "/control/resume"):
                store.set("paused", "1" if path.endswith("pause") else "0")
                return self.send(200, {"paused": store.get("paused")})
            self.send(404, {"error": "not found"})

        def do_GET(self):
            u = urlparse(self.path); qs = parse_qs(u.query)
            if u.path == "/api/status":
                counts = dict(store.q("SELECT state, COUNT(*) FROM inbox GROUP BY state"))
                lags = [r[0] for r in store.q("SELECT lag_ms FROM changes WHERE lag_ms IS NOT NULL ORDER BY id DESC LIMIT 200")]
                s = sorted(lags)
                return self.send(200, {"paused": store.get("paused", "1") == "1", "queued": counts.get("new", 0), "applied_events": counts.get("done", 0),
                                       "dlq": counts.get("dlq", 0), "changes": store.q("SELECT COUNT(*) FROM changes")[0][0],
                                       "last_position": store.get("last_position"),
                                       "lag_ms": {"last": lags[0] if lags else None, "p50": s[len(s) // 2] if s else None, "max": s[-1] if s else None}})
            if u.path == "/api/changes":
                lim = min(int(qs.get("limit", ["50"])[0]), 500); tbl = qs.get("table", [None])[0]
                sql = "SELECT id,tbl,op,position,commit_ms,applied_ms,lag_ms,report FROM changes" + (" WHERE tbl=?" if tbl else "") + " ORDER BY id DESC LIMIT ?"
                rows = store.q(sql, ((tbl, lim) if tbl else (lim,)))
                return self.send(200, [{"id": r[0], "table": r[1], "op": r[2], "position": r[3], "commit_ms": r[4], "applied_ms": r[5],
                                        "lag_ms": r[6], **json.loads(r[7])} for r in rows])
            if u.path == "/api/dlq":
                return self.send(200, [{"id": r[0], "error": r[1], "body": json.loads(r[2])} for r in store.q("SELECT id,error,body FROM inbox WHERE state='dlq'")])
            if u.path in ("/", "/index.html"):
                return self.send(200, raw=open(MONITOR, "rb").read(), ctype="text/html; charset=utf-8")
            if u.path == "/health":
                return self.send(200, {"ok": True})
            self.send(404, {"error": "not found"})
    return H


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=int(os.environ.get("CDC_PORT", "8090")))
    ap.add_argument("--db", default=os.environ.get("CDC_STATE", "/tmp/aw-cdc-consumer.sqlite"))
    ap.add_argument("--resume", action="store_true", help="start applying immediately")
    a = ap.parse_args()
    store = Store(a.db)
    if store.get("paused") is None or a.resume:
        store.set("paused", "0" if a.resume else "1")
    Applier(store).start()
    print("CDC consumer on :%d (paused=%s)" % (a.port, store.get("paused")), flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(store)).serve_forever()


if __name__ == "__main__":
    main()
