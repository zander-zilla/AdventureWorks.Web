"""C2-1: the CloudFront viewer-request function for /c1/ and /c2 (run with node, no AWS)."""
import json, os, shutil, subprocess

import pytest

FN = os.path.join(os.path.dirname(__file__), "..", "..", "infra", "modules", "showcase", "paths.js")


def run(uri):
    js = open(FN).read() + "\nconsole.log(JSON.stringify(handler({request: {uri: %s}})))" % json.dumps(uri)
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
@pytest.mark.parametrize("uri,expect", [
    ("/", {"uri": "/index.html"}), ("/c1/", {"uri": "/c1/index.html"}), ("/c1/app.js", {"uri": "/c1/app.js"}),
    ("/data/chapter2.json", {"uri": "/data/chapter2.json"}), ("/c1", 301), ("/c2", 302), ("/c2/", 302)])
def test_paths(uri, expect):
    r = run(uri)
    if isinstance(expect, int):
        assert r["statusCode"] == expect
    else:
        assert r == expect
