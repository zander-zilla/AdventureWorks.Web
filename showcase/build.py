#!/usr/bin/env python3
"""Build the static showcase site into showcase/dist (Phase 8, ADR 0009).

Copies site/ and the repo's sources of truth (no hand-maintained copies):
  design/mapping/mapping.json, docs/design/access-patterns.json, docs/migration/results.json,
  docs/design/load-stats.json -> dist/data/
  cdc/monitor/index.html (Phase 4 replication monitor) -> dist/monitor.html
  fixtures/replication-replay/*.json -> dist/api/status, dist/api/changes (static replay; S3 ignores query strings)
  config.json from --app-url / --monitor-api / --monitor-mode
"""
import argparse, datetime, json, os, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = {
    "mapping.json": "design/mapping/mapping.json",
    "access-patterns.json": "docs/design/access-patterns.json",
    "results.json": "docs/migration/results.json",
    "load-stats.json": "docs/design/load-stats.json",
}


def build(out, app_url="", monitor_api="", monitor_mode="replay", before_url=""):
    if os.path.isdir(out):
        shutil.rmtree(out)
    shutil.copytree(os.path.join(HERE, "site"), out)
    os.makedirs(os.path.join(out, "data"))
    for dst, src in DATA.items():
        with open(os.path.join(ROOT, src)) as f:
            json.load(f)  # fail the build on invalid JSON
        shutil.copy(os.path.join(ROOT, src), os.path.join(out, "data", dst))
    shutil.copy(os.path.join(ROOT, "cdc", "monitor", "index.html"), os.path.join(out, "monitor.html"))
    os.makedirs(os.path.join(out, "api"))
    for name in ("status", "changes"):
        shutil.copy(os.path.join(HERE, "fixtures", "replication-replay", name + ".json"), os.path.join(out, "api", name))
    try:
        commit = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    with open(os.path.join(out, "data", "build.json"), "w") as f:
        json.dump({"commit": commit, "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}, f)
    with open(os.path.join(out, "config.json"), "w") as f:
        json.dump({"appUrl": app_url, "beforeUrl": before_url, "monitorApi": monitor_api, "monitorMode": monitor_mode}, f, indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "dist"))
    ap.add_argument("--app-url", default=os.environ.get("SHOWCASE_APP_URL", ""))
    ap.add_argument("--before-url", default=os.environ.get("SHOWCASE_BEFORE_URL", ""))
    ap.add_argument("--monitor-api", default="")
    ap.add_argument("--monitor-mode", choices=["replay", "live"], default="replay")
    a = ap.parse_args()
    print("built", build(a.out, a.app_url, a.monitor_api, a.monitor_mode, a.before_url))
