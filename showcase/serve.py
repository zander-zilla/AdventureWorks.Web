#!/usr/bin/env python3
"""Serve showcase/dist locally. --live-api URL proxies /api/* to the Phase 4 CDC consumer (default replay files)."""
import argparse, functools, os, urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class H(SimpleHTTPRequestHandler):
    live_api = ""

    def do_GET(self):
        if self.live_api and self.path.startswith("/api/"):
            try:
                with urllib.request.urlopen(self.live_api.rstrip("/") + self.path, timeout=5) as r:
                    body = r.read()
                self.send_response(200)
            except Exception as e:  # consumer down -> surface it in the monitor
                body = ('{"error": "%s"}' % str(e).replace('"', "'")).encode()
                self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def guess_type(self, path):
        if "/api/" in path.replace(os.sep, "/"):
            return "application/json"
        return super().guess_type(path)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("SHOWCASE_PORT", "8088")))
    ap.add_argument("--live-api", default="")
    a = ap.parse_args()
    H.live_api = a.live_api
    print("showcase on http://localhost:%d (%s)" % (a.port, "live API " + a.live_api if a.live_api else "replay"), flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), functools.partial(H, directory=a.dir)).serve_forever()
