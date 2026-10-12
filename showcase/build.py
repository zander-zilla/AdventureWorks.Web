#!/usr/bin/env python3
"""Build the static showcase site into showcase/dist (Phase 8, ADR 0009; Chapter 2 layout C2-1).

C2-1 layout (build_site, the CLI default):
  dist/            Chapter 2 showcase (React bundle from src/web `npm run build:showcase` -> src/web/dist-showcase)
  dist/data/       Chapter 1 data files + business-processes.json, chapter2.json, adrs.json (sources of truth)
  dist/api/        recorded replication replay (CloudFront /api/* still serves the live monitor API on AWS)
  dist/c1/         Chapter 1 'Migration', frozen: --c1-dir <unzipped showcase-v1.0-migration> (the release asset /
                   showcase-freeze.yml); without it, built locally by build() below from the in-repo showcase/site
                   (byte-identical to tag v1.0-migration; asserted in CI). push-showcase.sh never uploads dist/c1/.

build() is the Chapter 1 builder (unchanged contract):

Copies site/ and the repo's sources of truth (no hand-maintained copies):
  design/mapping/mapping.json, docs/design/access-patterns.json, docs/migration/results.json,
  docs/design/load-stats.json -> dist/data/
  cdc/monitor/index.html (Phase 4 replication monitor) -> dist/monitor.html
  fixtures/replication-replay/*.json -> dist/api/status, dist/api/changes (static replay; S3 ignores query strings)
  config.json from --app-url / --monitor-api / --monitor-mode (replay | live = local consumer | aws = monitor API Lambda)
"""
import argparse, datetime, json, os, re, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = {
    "mapping.json": "design/mapping/mapping.json",
    "access-patterns.json": "docs/design/access-patterns.json",
    "results.json": "docs/migration/results.json",
    "load-stats.json": "docs/design/load-stats.json",
}
DATA_C2 = {
    "business-processes.json": "docs/business-processes/business-processes.json",
    "chapter2.json": "docs/chapter-2/chapter2.json",
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
    write_build_json(out)
    with open(os.path.join(out, "config.json"), "w") as f:
        json.dump({"appUrl": app_url, "beforeUrl": before_url, "monitorApi": monitor_api, "monitorMode": monitor_mode}, f, indent=1)
    return out


def write_build_json(out):
    try:
        commit = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    with open(os.path.join(out, "data", "build.json"), "w") as f:
        json.dump({"commit": commit, "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}, f)


ADR_STATUS = re.compile(r"Status:\s*\**([A-Za-z]+)")


def adrs():
    out = []
    d = os.path.join(ROOT, "docs", "adr")
    for name in sorted(os.listdir(d)):
        if not re.match(r"\d{4}-.*\.md$", name):
            continue
        text = open(os.path.join(d, name)).read()
        title = text.splitlines()[0].lstrip("# ").strip()
        m = ADR_STATUS.search(text)
        out.append({"id": name[:4], "title": title.split(":", 1)[-1].strip(), "status": m.group(1) if m else "",
                    "file": "docs/adr/" + name, "chapter": 2 if int(name[:4]) >= 10 else 1})
    return out


def build_site(out, app_url="", monitor_api="", monitor_mode="replay", before_url="", spa_url="", c1_dir=None, bundle=None):
    """Chapter 2 showcase at / with Chapter 1 frozen under /c1/ (C2-1)."""
    bundle = bundle or os.path.join(ROOT, "src", "web", "dist-showcase")
    if not os.path.isfile(os.path.join(bundle, "showcase.html")):
        raise SystemExit("missing %s: run `npm run build:showcase` in src/web first" % bundle)
    c1 = os.path.join(out, "c1")
    if os.path.isdir(out):
        shutil.rmtree(out)
    if c1_dir:
        shutil.copytree(c1_dir, c1)
    else:
        build(c1, app_url, monitor_api, monitor_mode, before_url)
    shutil.copytree(bundle, out, dirs_exist_ok=True)
    os.replace(os.path.join(out, "showcase.html"), os.path.join(out, "index.html"))
    os.makedirs(os.path.join(out, "data"), exist_ok=True)
    for dst, src in {**DATA, **DATA_C2}.items():
        with open(os.path.join(ROOT, src)) as f:
            json.load(f)
        shutil.copy(os.path.join(ROOT, src), os.path.join(out, "data", dst))
    with open(os.path.join(out, "data", "adrs.json"), "w") as f:
        json.dump(adrs(), f, indent=1)
    write_build_json(out)
    shutil.copy(os.path.join(ROOT, "cdc", "monitor", "index.html"), os.path.join(out, "monitor.html"))
    os.makedirs(os.path.join(out, "api"), exist_ok=True)
    for name in ("status", "changes"):
        shutil.copy(os.path.join(HERE, "fixtures", "replication-replay", name + ".json"), os.path.join(out, "api", name))
    with open(os.path.join(out, "config.json"), "w") as f:
        json.dump({"appUrl": app_url, "beforeUrl": before_url, "spaUrl": spa_url or (app_url.rstrip("/") + "/app/" if app_url else ""),
                   "monitorApi": monitor_api, "monitorMode": monitor_mode, "askTheData": False}, f, indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "dist"))
    ap.add_argument("--app-url", default=os.environ.get("SHOWCASE_APP_URL", ""))
    ap.add_argument("--before-url", default=os.environ.get("SHOWCASE_BEFORE_URL", ""))
    ap.add_argument("--monitor-api", default="")
    ap.add_argument("--monitor-mode", choices=["replay", "live", "aws"], default="replay")
    ap.add_argument("--spa-url", default=os.environ.get("SHOWCASE_SPA_URL", ""))
    ap.add_argument("--c1-dir", default="", help="frozen Chapter 1 build (unzipped showcase-v1.0-migration.zip)")
    ap.add_argument("--chapter1-only", action="store_true", help="Chapter 1 layout only (what tag v1.0-migration builds)")
    a = ap.parse_args()
    if a.chapter1_only:
        print("built", build(a.out, a.app_url, a.monitor_api, a.monitor_mode, a.before_url))
    else:
        print("built", build_site(a.out, a.app_url, a.monitor_api, a.monitor_mode, a.before_url, a.spa_url, a.c1_dir or None))
