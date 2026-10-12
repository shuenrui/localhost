"""MCP server (stdio, JSON-RPC 2.0) exposing the localhost CLI to AI agents.

Read-only tools only: nothing here installs or runs anything on the machine. The `run`
command stays in the terminal, where a person confirms each step.

Client config example (Claude Desktop / Claude Code / OpenCode style):
  {"command": "localhost", "args": ["mcp"]}
"""
import json
import sys

from . import __version__
from .data import Directory, load
from .fit import GROUPS, closest_miss, fit_all

TOOLS = [
    {"name": "detect", "description": "Read this machine's hardware: OS, CPU, RAM, GPU and VRAM, memory layout, "
     "free disk, installed engines and running local model servers.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "fit", "description": "Group every recipe in the localhost directory by whether it fits a machine: "
     "exact, similar, estimated, uncertain or unsupported. Uses this machine unless a profile is given.",
     "inputSchema": {"type": "object", "properties": {
         "model": {"type": "string", "description": "model family id, e.g. qwen3-8-27b"},
         "profile": {"type": "object", "description": "optional machine profile: os, gpu, gpuCount, ramGb, vramGb, unified (unified|separate), chip"},
         "include_unsupported": {"type": "boolean"}}}},
    {"name": "guide", "description": "Ordered setup steps for one recipe: engine install (from official docs), setup, "
     "start, check. Only steps with copyable=true are literal commands.",
     "inputSchema": {"type": "object", "properties": {"recipe": {"type": "string"}, "os": {"type": "string", "enum": ["macos", "linux", "windows"]}},
                     "required": ["recipe"]}},
    {"name": "show", "description": "The full record of one recipe: requirements, measurements with sources, caveats.",
     "inputSchema": {"type": "object", "properties": {"recipe": {"type": "string"}}, "required": ["recipe"]}},
    {"name": "recipes", "description": "List recipes, optionally filtered by model, hardware class or engine.",
     "inputSchema": {"type": "object", "properties": {"model": {"type": "string"}, "hardware": {"type": "string"}, "engine": {"type": "string"}}}},
    {"name": "models", "description": "List model families with recipe counts and the baseline recipe.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "check", "description": "Test a running local model server (OpenAI-compatible) with a cold prompt. "
     "Reports time to first token and decode speed.",
     "inputSchema": {"type": "object", "properties": {"endpoint": {"type": "string"}, "model": {"type": "string"}}}},
]


def _call(d, name, a):
    if name == "detect":
        from .detect import detect
        return detect()
    if name == "fit":
        from .detect import detect
        p = a.get("profile") or detect()
        p.setdefault("unified", "separate" if p.get("vramGb") else "")
        res = fit_all(d, p, model=a.get("model"))
        if not a.get("include_unsupported"):
            keep = [r for r in res if r["group"] != "unsupported"]
        else:
            keep = res
        return {"counts": {g: sum(1 for r in res if r["group"] == g) for g, _ in GROUPS},
                "results": keep, "closest_miss": closest_miss(res)}
    if name == "guide":
        from .guide import build
        return build(d, d.setup(a["recipe"]), a.get("os"))
    if name == "show":
        return d.setup(a["recipe"])
    if name == "recipes":
        rows = []
        for s in d.setups:
            if a.get("model") and s.get("model") != a["model"]:
                continue
            if a.get("hardware") and a["hardware"] not in d.hw_ids(s):
                continue
            if a.get("engine") and d.engine_id(s) != a["engine"]:
                continue
            rows.append({"id": s["id"], "title": s.get("title"), "model": s.get("model"), "engine": d.engine_id(s),
                         "hardware": d.hw_ids(s), "memory_gb": (s.get("requirements") or {}).get("memory_gb")})
        return rows
    if name == "models":
        return [{"id": m, "name": d.model(m).get("name"),
                 "recipes": sum(1 for s in d.setups if s.get("model") == m),
                 "baseline_recipe": (d.model(m).get("practical_baseline") or {}).get("setup")} for m in d.order]
    if name == "check":
        from .check import check
        return check(a.get("endpoint"), a.get("model"))
    raise KeyError("unknown tool %r" % name)


def _reply(id_, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id_}
    if error:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg, default=str) + "\n")
    sys.stdout.flush()


def serve(data_path=None):
    d = None
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            _reply(None, error={"code": -32700, "message": "parse error"})
            continue
        method, id_, params = req.get("method"), req.get("id"), req.get("params") or {}
        if id_ is None:  # notification (e.g. notifications/initialized)
            continue
        try:
            if method == "initialize":
                _reply(id_, {"protocolVersion": params.get("protocolVersion") or "2025-06-18",
                             "capabilities": {"tools": {}},
                             "serverInfo": {"name": "localhost", "version": __version__},
                             "instructions": "Use detect, then fit, then guide. Only steps with copyable=true are "
                                             "literal commands; never invent commands. This server never runs "
                                             "anything on the machine except a test prompt in `check`."})
            elif method == "ping":
                _reply(id_, {})
            elif method == "tools/list":
                _reply(id_, {"tools": TOOLS})
            elif method == "tools/call":
                if d is None:
                    d = Directory(load(data_path)[0])
                try:
                    res = _call(d, params.get("name"), params.get("arguments") or {})
                    _reply(id_, {"content": [{"type": "text", "text": json.dumps(res, default=str)}], "isError": False})
                except (KeyError, ValueError, RuntimeError) as e:
                    _reply(id_, {"content": [{"type": "text", "text": "error: %s" % (e.args[0] if e.args else e)}], "isError": True})
            else:
                _reply(id_, error={"code": -32601, "message": "method not found: %s" % method})
        except Exception as e:  # never crash the server on one bad request
            _reply(id_, error={"code": -32603, "message": str(e)})
    return 0
