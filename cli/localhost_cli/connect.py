"""Connect a local model to an existing chat/coding UI.

v0 supports OpenCode. Config shape follows https://opencode.ai/docs/providers/
(custom provider with "@ai-sdk/openai-compatible", options.baseURL, models.<id>.limit).
Default is a dry run that prints the config. --write merges it into the config file and
keeps a timestamped backup of the old file.
"""
import json
import os
import shutil
import time
import urllib.request

OPENCODE_DEFAULT = os.path.join(os.path.expanduser("~"), ".config", "opencode", "opencode.json")
PROVIDER_ID = "localhost"


def ollama_num_ctx(endpoint, model):
    """Ollama only: read num_ctx from the model's parameters, if one is set."""
    base = endpoint.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    try:
        req = urllib.request.Request(base + "/api/show", data=json.dumps({"model": model}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            info = json.load(r)
    except Exception:
        return None
    for line in (info.get("parameters") or "").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "num_ctx" and parts[1].isdigit():
            return int(parts[1])
    return None


def opencode_config(endpoint, model, context=None, output=None, engine=None, label=None):
    warnings = []
    if context is None and engine == "ollama":
        context = ollama_num_ctx(endpoint, model)
        if context is None:
            warnings.append(
                "Ollama: this model has no num_ctx set, so Ollama uses its small default context. "
                "Coding agents send long prompts and will be cut off. Set a longer context "
                "(the recipe's own step, e.g. a Modelfile with num_ctx), then re-run with --context N.")
    entry = {"name": label or ("%s (local)" % model)}
    if context:
        entry["limit"] = {"context": int(context), "output": int(output or min(8192, int(context) // 4))}
    else:
        warnings.append("No context limit set: OpenCode cannot tell how much room is left. Pass --context N.")
    cfg = {"$schema": "https://opencode.ai/config.json",
           "provider": {PROVIDER_ID: {"npm": "@ai-sdk/openai-compatible",
                                      "name": "localhost" + (" (%s)" % engine if engine else ""),
                                      "options": {"baseURL": endpoint.rstrip("/")},
                                      "models": {model: entry}}}}
    return cfg, warnings


def merge_write(cfg, path=OPENCODE_DEFAULT):
    """Merge our provider into an existing config. Returns (path, backup_path or None)."""
    existing = {}
    backup = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        try:
            existing = json.loads(txt) if txt.strip() else {}
        except ValueError:
            raise RuntimeError("%s is not plain JSON (comments?). Not touching it; paste the printed "
                               "config in by hand." % path)
        backup = "%s.bak-%d" % (path, int(time.time()))
        shutil.copy2(path, backup)
    existing.setdefault("$schema", cfg["$schema"])
    prov = existing.setdefault("provider", {})
    ours = cfg["provider"][PROVIDER_ID]
    cur = prov.setdefault(PROVIDER_ID, {})
    cur.update({k: v for k, v in ours.items() if k != "models"})
    cur.setdefault("models", {}).update(ours["models"])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return path, backup
