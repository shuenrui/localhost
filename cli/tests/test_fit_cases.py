#!/usr/bin/env python3
"""Behaviour checks for the 2026-10-12 fit fixes. Run: python3 tests/test_fit_cases.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from localhost_cli.data import Directory, _parse  # noqa: E402
from localhost_cli.fit import classify  # noqa: E402

SITE = os.path.join(HERE, "..", "..", "directory", "site", "index.html")
d = Directory(_parse(open(SITE, encoding="utf-8").read()))


def prof(**kw):
    p = {"os": "linux", "chip": "", "gpu": "", "gpuCount": 1, "ramGb": None, "vramGb": None, "unified": "separate", "deviceId": ""}
    p.update(kw)
    return p


def group(sid, p):
    return classify(d.setup(sid), p, d.hardware)


CASES = [
    # 1. Recipes measured on a 24 GB card fit a 24 GB card (the reserve no longer comes off VRAM).
    ("qwen38-27b-atomicchat-gguf-llamacpp-4090-mtp", prof(gpu="RTX 4090", vramGb=24, ramGb=64), "similar"),
    ("qwen38-27b-unsloth-gguf-ollama-3090", prof(gpu="RTX 3090", vramGb=24, ramGb=32), "similar"),
    # 2. Offload recipes count system RAM: 110 GB needs 24 GB VRAM + enough RAM.
    ("qwen38-flash-next-unsloth-gguf-llamacpp-4090-hybrid", prof(gpu="RTX 4090", vramGb=24, ramGb=64), "unsupported"),
    ("qwen38-flash-next-unsloth-gguf-llamacpp-4090-hybrid", prof(gpu="RTX 4090", vramGb=24, ramGb=128), "similar"),
    # 3. A 2-GPU recipe is not "verified on similar hardware" for a 1-GPU machine.
    ("qwen38-27b-atomicchat-gguf-q4-2x-rtx5090", prof(gpu="RTX 5090", vramGb=32, ramGb=64), "estimated"),
    ("qwen38-27b-atomicchat-gguf-q4-2x-rtx5090", prof(gpu="RTX 5090", gpuCount=2, vramGb=64, ramGb=128), "similar"),
    # 3b. A recipe that fits on the GPU alone is judged on VRAM only (no "72 GB spare" from adding RAM).
    ("qwen38-27b-unsloth-gguf-lm-studio", prof(gpu="RTX 4090", vramGb=24, ramGb=64), "similar"),
    # 4. Unified memory still keeps the OS reserve (macOS 6 GB): a 64 GB Mac has 58 GB.
    ("qwen38-flash-next-atomicchat-gguf-llamacpp-mac64", prof(os="macos", chip="Apple M4 Max", ramGb=64, unified="unified"), None),
]

fails = 0
for sid, p, want in CASES:
    r = group(sid, p)
    ok = want is None or r["group"] == want
    if r.get("memory_model") != "offload" and p.get("unified") == "separate" and r["req"] is not None and r["avail"] is not None:
        ok = ok and r["avail"] == p["vramGb"]  # GPU-only recipes are judged on VRAM alone
    fails += not ok
    print("%s %-55s want=%-11s got=%-11s %s" % ("ok  " if ok else "FAIL", sid[:55], want, r["group"], r["verdict"][:90]))
tight = group("qwen38-27b-atomicchat-gguf-llamacpp-4090-mtp", prof(gpu="RTX 4090", vramGb=24, ramGb=64))
if "Tight" not in tight["verdict"]:
    fails += 1
    print("FAIL tight-note missing")
print("%d failures" % fails)
sys.exit(1 if fails else 0)
