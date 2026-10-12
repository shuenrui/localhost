"""Fit check: a port of the site's classify() and memFit() (site_src/app.js).

Keep this in step with app.js. tests/test_fit_parity.py runs the site's own JS beside
it on every recipe. One deliberate addition: a machine with no GPU and no unified memory
gets the arch family "cpu". The site's default ("nvidia") would wrongly mark every NVIDIA
recipe as architecture-compatible on a CPU-only box. The site has no way to enter such a
profile, so parity is unaffected.
"""
import re

GROUPS = [
    ("exact", "Verified on this exact machine"),
    ("similar", "Verified on similar hardware"),
    ("estimated", "Likely to fit (estimate)"),
    ("uncertain", "Uncertain"),
    ("unsupported", "Will not fit as recorded"),
]


def gb(v):
    if v is None:
        return None
    return ("%d GB" % round(v)) if v >= 100 else ("%s GB" % (round(v * 10) / 10)).replace(".0 GB", " GB")


def default_reserve(p, override=None):
    if override is not None:
        return override
    return 6 if p.get("os") == "macos" else 4 if p.get("os") == "linux" else 8


def available_gb(p):
    if p.get("unified") == "separate":
        return p.get("vramGb")
    if p.get("ramGb") is not None:
        return p["ramGb"]
    return p.get("vramGb")


def profile_classes(p, HW):
    if p.get("deviceId"):
        a = (HW.get(p["deviceId"]) or {}).get("arch")
        return [p["deviceId"]] + [i for i in HW if i != p["deviceId"] and HW[i].get("arch") == a]
    ram = p.get("ramGb")
    chip = "%s %s" % (p.get("chip") or "", p.get("gpu") or "")
    if re.search(r"GB10|Grace|Spark|PGX", chip, re.I):
        return ["dgx-spark", "thinkstation-pgx"]
    if re.search(r"Ryzen AI Max|Radeon 8060S|Strix Halo|gfx1151", chip, re.I):
        return ["strix-halo"]
    if p.get("os") == "macos" or re.search(r"Apple|M[1-9]\b", chip, re.I):
        if ram is not None and ram >= 200:
            return ["mac-256gb", "mac-128gb", "mac-64gb"]
        if ram is not None and ram >= 96:
            return ["mac-128gb", "mac-64gb"]
        return ["mac-64gb"]
    if p.get("unified") == "cpu-only":
        return []
    if re.search(r"\b5090\b", chip, re.I):
        return ["rtx-5090", "gpu-multigpu-72gb", "gpu-24gb"] if (p.get("gpuCount") or 1) > 1 else ["rtx-5090", "gpu-24gb"]
    if re.search(r"RTX PRO 6000|PRO 6000 Blackwell|RTX 6000", chip, re.I):
        return ["rtx-pro-6000"]
    if (p.get("gpuCount") or 1) > 1:
        return ["gpu-multigpu-72gb", "gpu-24gb"]
    return ["gpu-24gb"]


def arch_family(hw_id, HW):
    a = (HW.get(hw_id) or {}).get("arch") or ""
    if re.search(r"Metal", a, re.I):
        return "apple"
    if re.search(r"RDNA|AMD|gfx", a, re.I):
        return "amd"
    return "nvidia"


FAMILY_LABEL = {"apple": "Apple Silicon", "amd": "AMD iGPU", "nvidia": "NVIDIA hardware", "cpu": "CPU only"}


def profile_arch(p, HW):
    if p.get("deviceId"):
        return arch_family(p["deviceId"], HW)
    t = "%s %s" % (p.get("chip") or "", p.get("gpu") or "")
    if p.get("os") == "macos" or re.search(r"Apple|M[1-9]\b", t, re.I):
        return "apple"
    if re.search(r"Ryzen AI Max|Radeon 8060S|Strix Halo|gfx1151", t, re.I):
        return "amd"
    if p.get("unified") == "cpu-only":
        return "cpu"
    return "nvidia"


def mem_fit(s, p, reserve):
    """Port of memFit() in app.js. See the comment there for the rules."""
    rq = s.get("requirements") or {}
    req, min_v = rq.get("memory_gb"), rq.get("min_vram_gb")
    if p.get("unified") == "separate" and p.get("vramGb") is not None:
        vram = p["vramGb"]
        host = None if p.get("ramGb") is None else max(0, p["ramGb"] - reserve)
        offload = min_v is not None and req is not None and min_v < req and req > vram
        if offload and host is not None:
            return {"req": req, "avail": vram + host, "fits": req is None or (vram >= min_v and vram + host >= req),
                    "kind": "offload", "vram": vram, "host": host}
        return {"req": req, "avail": vram, "fits": req is None or req <= vram, "kind": "gpu", "vram": vram, "host": host}
    raw = available_gb(p)
    avail = None if raw is None else max(0, raw - reserve)
    return {"req": req, "avail": avail, "fits": req is None or avail is None or req <= avail, "kind": "shared"}


def classify(s, p, HW, reserve=None, context=8192, concurrency=1):
    reserve = default_reserve(p, reserve)
    m = mem_fit(s, p, reserve)
    req, avail = m["req"], m["avail"]
    classes = profile_classes(p, HW)
    entries = [(h["id"], h.get("count") or 1) if isinstance(h, dict) else (h, 1) for h in s.get("hardware") or []]
    hw = [i for i, _ in entries]
    # Entries like {"id": "rtx-5090", "count": 2} ran on 2 devices: match only a machine with that many.
    have = p.get("gpuCount") or 1
    on_hw = [i for i, n in entries if i in classes and n <= have]
    measured = len(s.get("measurements") or []) > 0
    exact = bool(any((HW.get(i) or {}).get("measured_by_us") is True for i in on_hw)
                 and p.get("deviceId") and p["deviceId"] in on_hw and measured)
    parch = profile_arch(p, HW)
    arch_ok = any(arch_family(i, HW) == parch for i in hw)

    if req is not None and avail is not None and not m["fits"]:
        group = "unsupported"
        if m["kind"] == "offload":
            verdict = "Will not fit as recorded: needs %s (at least %s on the GPU); you have %s GPU + %s RAM after a %s reserve." % (
                gb(req), gb((s.get("requirements") or {}).get("min_vram_gb")), gb(m["vram"]), gb(round(m["host"] * 10) / 10), gb(reserve))
        elif m["kind"] == "gpu":
            verdict = "Will not fit as recorded: needs %s; your GPU memory is %s." % (gb(req), gb(m["vram"]))
        else:
            verdict = "Will not fit as recorded: needs %s, you have %s after a %s reserve." % (
                gb(req), gb(round(avail * 10) / 10), gb(reserve))
    elif exact:
        group, verdict = "exact", "Verified on this exact machine."
    elif on_hw and (measured or req is not None):
        group = "similar"
        verdict = "Verified on similar hardware: recorded on %s." % " and ".join(
            (HW.get(i) or {}).get("name", i) for i in on_hw)
        if req is not None and avail is not None:
            verdict += " Leaves about %s free." % gb(round((avail - req) * 10) / 10)
    elif req is not None and avail is not None:
        group = "estimated"
        verdict = "Likely to fit with about %s spare at %d context, %d stream(s). Not tested on this exact machine." % (
            gb(round((avail - req) * 10) / 10), context, concurrency)
    else:
        group = "uncertain"
        verdict = ("Uncertain: this recipe records no memory requirement." if req is None
                   else "Uncertain: your machine's memory is unknown.")
    if not arch_ok:
        fams = sorted({FAMILY_LABEL[arch_family(i, HW)] for i in hw})
        verdict += " Note: only recorded on %s; you have %s. The engine path, not memory, is the constraint." % (
            " and ".join(fams), FAMILY_LABEL[parch])
        if group == "estimated":
            group = "uncertain"
    if group != "unsupported" and m["kind"] == "gpu" and req is not None and m["vram"] - req < 1:
        verdict += " Tight: uses all of the card's memory; close other programs using the GPU."
    return {"group": group, "verdict": verdict, "req": req, "avail": avail, "reserve": reserve,
            "on_hw": on_hw, "exact": exact, "arch_ok": arch_ok, "memory_model": m["kind"]}


def fit_all(directory, p, model=None, reserve=None):
    out = []
    for s in directory.setups:
        if model and s.get("model") != model:
            continue
        r = classify(s, p, directory.hardware, reserve=reserve)
        r["id"], r["title"], r["model"] = s["id"], s.get("title"), s.get("model")
        r["engine"] = directory.engine_id(s)
        run = s.get("run") or {}
        r["has_command"] = bool(run.get("command") or any(
            (st or {}).get("kind") == "cmd" for st in (run.get("steps") or [])))
        out.append(r)
    order = {g: i for i, (g, _) in enumerate(GROUPS)}
    out.sort(key=lambda r: (order[r["group"]], -(r["req"] or 0)))
    return out


def closest_miss(results):
    """For machines where little fits: the smallest recorded requirement that does not fit."""
    miss = [r for r in results if r["group"] == "unsupported" and r["req"] is not None]
    return min(miss, key=lambda r: r["req"]) if miss else None
