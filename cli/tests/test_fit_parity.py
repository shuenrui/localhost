#!/usr/bin/env python3
"""Parity test: run the SITE's own classify() (extracted from site_src/app.js, run in
node) and the CLI's Python port on the same profiles, and compare every recipe's group.

Usage: python3 tests/test_fit_parity.py [path/to/site/index.html]
Needs node. Exit 1 on any mismatch.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, ".."))
from localhost_cli.data import Directory, _parse  # noqa: E402
from localhost_cli.fit import classify  # noqa: E402

APP = os.path.join(REPO, "directory", "site_src", "app.js")
SITE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "directory", "site", "index.html")
FUNCS = ["gb", "ctx", "uniq", "blankProfile", "defaultReserve", "availableGb", "profileClasses",
         "archFamily", "familyLabel", "profileArch", "hwRefId", "hwRefCount", "memFit", "hwEntries", "classify"]

PROFILES = {
    "4090_64": {"os": "linux", "gpu": "RTX 4090", "gpuCount": 1, "ramGb": 64, "vramGb": 24, "unified": "separate"},
    "2x3090": {"os": "linux", "gpu": "RTX 3090", "gpuCount": 2, "ramGb": 128, "vramGb": 48, "unified": "separate"},
    "mac128": {"os": "macos", "chip": "Apple M4 Max", "gpuCount": 1, "ramGb": 128, "unified": "unified"},
    "mac16": {"os": "macos", "chip": "Apple M4", "gpuCount": 1, "ramGb": 16, "unified": "unified"},
    "strix": {"os": "linux", "chip": "AMD Ryzen AI Max+ 395", "gpu": "Radeon 8060S", "ramGb": 128, "unified": "unified"},
    "spark": {"os": "linux", "chip": "NVIDIA GB10", "ramGb": 128, "unified": "unified"},
    "5090win": {"os": "windows", "gpu": "RTX 5090", "gpuCount": 1, "ramGb": 64, "vramGb": 32, "unified": "separate"},
    "dev_strix": {"os": "linux", "ramGb": 128, "unified": "unified", "deviceId": "strix-halo"},
    "pro6000": {"os": "linux", "gpu": "RTX PRO 6000 Blackwell", "gpuCount": 1, "ramGb": 256, "vramGb": 96, "unified": "separate"},
    "4090_128": {"os": "linux", "gpu": "RTX 4090", "gpuCount": 1, "ramGb": 128, "vramGb": 24, "unified": "separate"},
    "2x5090": {"os": "linux", "gpu": "RTX 5090", "gpuCount": 2, "ramGb": 128, "vramGb": 64, "unified": "separate"},
    "3060_16": {"os": "windows", "gpu": "RTX 3060", "gpuCount": 1, "ramGb": 16, "vramGb": 12, "unified": "separate"},
    "vram_only": {"os": "linux", "gpu": "RTX 4090", "gpuCount": 1, "vramGb": 24, "unified": "separate"},
}


def extract(src, name):
    m = re.search(r"^function %s\s*\(" % re.escape(name), src, re.M)
    if not m:
        return ""
    i = src.index("{", m.end())
    depth = 0
    for j in range(i, len(src)):
        depth += {"{": 1, "}": -1}.get(src[j], 0)
        if depth == 0:
            return src[m.start(): j + 1]
    raise ValueError(name)


def main():
    src = open(APP, encoding="utf-8").read()
    data = _parse(open(SITE, encoding="utf-8").read())
    d = Directory(data)
    js = "\n".join(extract(src, f) for f in FUNCS)
    harness = js + """
var DATA = %s, HW = DATA.hardware, SETUPS = DATA.setups, P = %s;
/* same load-time normalization as app.js: keep counts in hwRefs, ids in hardware */
SETUPS.forEach(function (s) {
  s.hwRefs = (s.hardware || []).map(function (h) { return { id: hwRefId(h), count: hwRefCount(h) }; })
    .filter(function (r) { return r.id; });
  s.hardware = s.hwRefs.map(function (r) { return r.id; });
});
var state = {assume: {context: 8192, concurrency: 1, reserve: null}};
function modelOf(s) { return DATA.models[s.model] || {}; }
var out = {};
for (var k in P) { var p = Object.assign(blankProfile(), P[k]); out[k] = {};
  SETUPS.forEach(function (s) { out[k][s.id] = classify(s, p).group; }); }
console.log(JSON.stringify(out));
""" % (json.dumps(data), json.dumps(PROFILES))
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        path = f.name
    site = json.loads(subprocess.run(["node", path], capture_output=True, text=True, check=True).stdout)
    os.unlink(path)
    bad = 0
    total = 0
    for k, prof in PROFILES.items():
        base = {"os": "", "chip": "", "gpu": "", "gpuCount": None, "ramGb": None, "vramGb": None, "unified": "", "deviceId": ""}
        base.update(prof)
        for s in d.setups:
            total += 1
            py = classify(s, base, d.hardware)["group"]
            if py != site[k][s["id"]]:
                bad += 1
                print("MISMATCH %s %s: site=%s cli=%s" % (k, s["id"], site[k][s["id"]], py))
    print("parity: %d/%d recipe-profile pairs match across %d profiles" % (total - bad, total, len(PROFILES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
