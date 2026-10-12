"""Read this machine's hardware without asking the user.

Every probe is read-only and optional: a missing tool means "unknown", never a crash.
Output matches the site's My Hardware profile fields (os, chip, gpu, gpuCount, ramGb,
vramGb, unified, diskGb, driver), plus what is installed and running.
"""
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import urllib.request

ENGINE_BINS = {
    "ollama": ["ollama"],
    "llama-cpp": ["llama-server", "llama-cli", "llama"],
    "vllm": ["vllm"],
    "sglang": ["sglang"],
    "lm-studio": ["lms"],
    "mlx-lm": ["mlx_lm.server"],
}
# Common default ports for OpenAI-compatible local servers.
SERVER_PORTS = [
    ("ollama", 11434), ("llama-cpp", 8080), ("vllm", 8000),
    ("lm-studio", 1234), ("sglang", 30000),
]


def _run(cmd, timeout=8):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def _gb(nbytes):
    return round(nbytes / 1024 ** 3, 1)


def _ram_gb(osname):
    if osname == "linux":
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return _gb(int(line.split()[1]) * 1024)
        except OSError:
            return None
    if osname == "macos":
        v = _run(["sysctl", "-n", "hw.memsize"]).strip()
        return _gb(int(v)) if v.isdigit() else None
    if osname == "windows":
        try:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("m", ctypes.c_ulong), ("t", ctypes.c_ulonglong),
                            ("a", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
            ms = MS()
            ms.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return _gb(ms.t)
        except Exception:
            return None
    return None


def _cpu_name(osname):
    if osname == "macos":
        return _run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip() or None
    if osname == "linux":
        try:
            with open("/proc/cpuinfo") as f:
                txt = f.read()
            m = re.search(r"^(model name|Hardware|Model)\s*:\s*(.+)$", txt, re.M)
            if m:
                return m.group(2).strip()
        except OSError:
            pass
        out = _run(["lscpu"])
        m = re.search(r"^Model name:\s*(.+)$", out, re.M)
        return m.group(1).strip() if m else None
    return platform.processor() or None


def _nvidia():
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits"])
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3 and parts[1].replace(".", "").isdigit():
            gpus.append({"name": parts[0], "vram_gb": round(float(parts[1]) / 1024, 1), "driver": parts[2]})
    return gpus


def _amd():
    out = _run(["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json"])
    gpus = []
    try:
        for card, v in json.loads(out).items():
            name = v.get("Card Series") or v.get("Card series") or v.get("Card model") or card
            total = v.get("VRAM Total Memory (B)")
            gpus.append({"name": name, "vram_gb": _gb(int(total)) if total else None, "driver": "rocm"})
    except Exception:
        pass
    return gpus


def _port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def running_servers():
    found = []
    for engine, port in SERVER_PORTS:
        if not _port_open(port):
            continue
        base = "http://127.0.0.1:%d" % port
        models = []
        try:
            with urllib.request.urlopen(base + "/v1/models", timeout=3) as r:
                models = [m.get("id") for m in json.load(r).get("data", [])]
        except Exception:
            pass
        found.append({"engine_guess": engine, "endpoint": base + "/v1", "models": models})
    return found


def detect():
    sysname = platform.system().lower()
    osname = {"darwin": "macos"}.get(sysname, sysname)
    arch = platform.machine().lower()
    chip = _cpu_name(osname)
    ram = _ram_gb(osname)
    p = {"os": osname, "arch": arch, "chip": chip, "gpu": "", "gpuCount": 0, "ramGb": ram,
         "vramGb": None, "unified": "", "diskGb": None, "driver": "", "gpus": [], "notes": []}

    gpus = _nvidia() or _amd()
    is_apple = osname == "macos" and arch in ("arm64", "aarch64")
    strix = bool(re.search(r"Ryzen AI Max|Strix Halo", chip or "", re.I))
    gb10 = bool(re.search(r"GB10|Grace", (chip or "") + " " + " ".join(g["name"] for g in gpus), re.I))

    if is_apple:
        p.update(gpu=chip or "Apple GPU", gpuCount=1, vramGb=ram, unified="unified")
        p["notes"].append("Apple silicon: GPU shares system memory (unified).")
    elif strix or gb10:
        p.update(unified="unified", vramGb=ram, gpuCount=1,
                 gpu=(gpus[0]["name"] if gpus else ("Radeon 8060S" if strix else "GB10")))
        p["notes"].append("Unified-memory APU: the GPU can use most of system RAM.")
    elif gpus:
        p.update(gpus=gpus, gpuCount=len(gpus), gpu=gpus[0]["name"], unified="separate",
                 vramGb=round(sum(g["vram_gb"] or 0 for g in gpus), 1), driver=gpus[0]["driver"])
        if len({g["name"] for g in gpus}) > 1:
            p["notes"].append("Mixed GPUs: fit uses total VRAM; real splits may be lower.")
    else:
        p["unified"] = "cpu-only"
        p["notes"].append("No supported GPU found (checked nvidia-smi, rocm-smi). "
                          "Recipes in the directory assume a GPU or Apple/AMD unified memory.")

    try:
        p["diskGb"] = _gb(shutil.disk_usage(os.path.expanduser("~")).free)
    except OSError:
        pass
    p["engines_installed"] = {e: next((shutil.which(b) for b in bins if shutil.which(b)), None)
                              for e, bins in ENGINE_BINS.items()}
    p["engines_installed"] = {k: v for k, v in p["engines_installed"].items() if v}
    p["servers_running"] = running_servers()
    return p
