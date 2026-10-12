"""localhost: find, set up, check and connect local LLMs, using the localhost directory.

Every command takes --json, for agents. Commands never invent install or run steps:
they print what the directory records, and say plainly when it records nothing.
"""
import argparse
import json
import sys

from . import __version__
from .data import Directory, DataError, load
from .detect import detect
from .fit import GROUPS, closest_miss, fit_all, gb

AGENT_NOTE = ("Agents: start with `localhost detect --json`, then `localhost fit --json`, then "
              "`localhost guide <recipe> --json`. Copy only steps marked copyable; never invent commands.")


def out(args, obj, text):
    if args.json:
        json.dump(obj, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text.rstrip() + "\n")


def get_dir(args):
    data, meta = load(args.data, refresh=getattr(args, "refresh", False))
    return Directory(data), meta


def cmd_data(args):
    d, meta = get_dir(args)
    info = {"generated": d.raw.get("generated"), "counts": d.raw.get("counts"), **meta}
    out(args, info, "Directory generated %s from %s%s\n%s" % (
        info["generated"], meta["source"], " (cached)" if meta.get("cached") else "",
        ", ".join("%s %s" % (v, k) for k, v in (info["counts"] or {}).items())))


def cmd_models(args):
    d, _ = get_dir(args)
    rows = []
    for mid in d.order:
        m = d.model(mid)
        n = sum(1 for s in d.setups if s.get("model") == mid)
        rows.append({"id": mid, "name": m.get("name"), "architecture": m.get("architecture"),
                     "context": m.get("context"), "recipes": n,
                     "baseline_recipe": (m.get("practical_baseline") or {}).get("setup")})
    out(args, rows, "\n".join("%-28s %-30s %3d recipes" % (r["id"], r["name"], r["recipes"]) for r in rows))


def cmd_recipes(args):
    d, _ = get_dir(args)
    rows = []
    for s in d.setups:
        if args.model and s.get("model") != args.model:
            continue
        if args.hardware and args.hardware not in d.hw_ids(s):
            continue
        if args.engine and d.engine_id(s) != args.engine:
            continue
        run = s.get("run") or {}
        has = bool(run.get("command") or any((st or {}).get("kind") == "cmd" for st in run.get("steps") or []))
        if args.runnable and not has:
            continue
        rows.append({"id": s["id"], "title": s.get("title"), "model": s.get("model"),
                     "engine": d.engine_id(s), "hardware": d.hw_ids(s),
                     "memory_gb": (s.get("requirements") or {}).get("memory_gb"),
                     "has_command": has, "status": s.get("status")})
    out(args, rows, "\n".join("%-62s %-10s %6s  %s" % (r["id"][:62], r["engine"],
                              gb(r["memory_gb"]) or "?", "cmd" if r["has_command"] else "-") for r in rows)
        + "\n%d recipes" % len(rows))


def cmd_show(args):
    d, _ = get_dir(args)
    s = d.setup(args.recipe)
    lines = [s.get("title", s["id"]), "id: %s" % s["id"], "model: %s   engine: %s   hardware: %s" % (
        s.get("model"), d.engine_id(s), ", ".join(d.hw_ids(s))),
        "needs: %s" % json.dumps({k: v for k, v in (s.get("requirements") or {}).items()
                                 if k in ("memory_gb", "disk_gb", "min_vram_gb")})]
    for m in s.get("measurements") or []:
        lines.append("measured: %s %s %s (%s, %s)" % (m.get("metric"), m.get("value"), m.get("unit"),
                                                    m.get("provenance"), m.get("date")))
    for src in s.get("sources") or []:
        lines.append("source: %s" % (src.get("url") if isinstance(src, dict) else src))
    out(args, s, "\n".join(lines))


def profile_from_args(args):
    p = detect() if not args.no_detect else {"os": "", "chip": "", "gpu": "", "gpuCount": None,
                                             "ramGb": None, "vramGb": None, "unified": ""}
    for flag, key in (("os", "os"), ("chip", "chip"), ("gpu", "gpu"), ("gpus", "gpuCount"),
                      ("ram", "ramGb"), ("vram", "vramGb"), ("unified", "unified"), ("device", "deviceId")):
        v = getattr(args, flag, None)
        if v is not None:
            p[key] = v
    if args.gpu and args.unified is None and p.get("unified") in ("", "cpu-only"):
        p["unified"] = "separate"
    return p


def cmd_detect(args):
    p = detect()
    servers = p.get("servers_running") or []
    text = ["os: %s (%s)" % (p["os"], p["arch"]), "cpu: %s" % p["chip"], "ram: %s" % gb(p["ramGb"]),
            "gpu: %s x%s, vram %s, memory %s" % (p["gpu"] or "none", p["gpuCount"], gb(p["vramGb"]), p["unified"]),
            "free disk: %s" % gb(p["diskGb"]),
            "engines installed: %s" % (", ".join(p["engines_installed"]) or "none"),
            "servers running: %s" % (", ".join("%s %s (%d models)" % (s["engine_guess"], s["endpoint"], len(s["models"]))
                                               for s in servers) or "none")]
    text += ["note: %s" % n for n in p["notes"]]
    out(args, p, "\n".join(text))


def cmd_fit(args):
    d, _ = get_dir(args)
    p = profile_from_args(args)
    res = fit_all(d, p, model=args.model, reserve=args.reserve)
    miss = closest_miss(res)
    counts = {g: sum(1 for r in res if r["group"] == g) for g, _ in GROUPS}
    payload = {"profile": {k: p.get(k) for k in ("os", "chip", "gpu", "gpuCount", "ramGb", "vramGb", "unified", "deviceId")},
               "counts": counts, "results": res, "closest_miss": miss}
    text = ["Machine: %s, %s, %s, memory %s" % (p.get("os"), p.get("gpu") or p.get("chip"),
                                               gb(p.get("vramGb") if p.get("unified") == "separate" else p.get("ramGb")),
                                               p.get("unified") or "?"), ""]
    for g, label in GROUPS:
        rows = [r for r in res if r["group"] == g]
        if not rows or (g == "unsupported" and not args.all):
            continue
        text.append("%s (%d)" % (label, len(rows)))
        for r in rows[: (None if args.all else 12)]:
            text.append("  %-60s %6s %s" % (r["id"][:60], gb(r["req"]) or "?", "cmd" if r["has_command"] else ""))
        text.append("")
    text.append("Will not fit as recorded: %d (show with --all)" % counts["unsupported"])
    if miss and counts["exact"] + counts["similar"] + counts["estimated"] <= 3:
        text.append("Closest that does not fit: %s needs %s." % (miss["id"], gb(miss["req"])))
    text.append("Next: localhost guide <recipe-id>")
    out(args, payload, "\n".join(text))


def cmd_guide(args):
    d, _ = get_dir(args)
    s = d.setup(args.recipe)
    eid = d.engine_id(s)
    eng = d.engines.get(eid) or {}
    e_in = s.get("engine") if isinstance(s.get("engine"), dict) else {}
    run = s.get("run") or {}
    steps = []
    steps.append({"phase": "engine", "copyable": False,
                  "text": "Install %s. The directory does not record install commands; use the engine's own "
                          "instructions: %s" % (eng.get("name", eid), eng.get("url") or "(no link recorded)")})
    if e_in.get("requires_fork"):
        steps.append({"phase": "engine", "copyable": False,
                      "text": "Heads up: this recipe needs a modified engine build, not the standard release. %s"
                              % (e_in.get("config") or "")})
    seen = set()
    for st in run.get("steps") or []:
        st = st or {}
        txt = st.get("text") or ""
        steps.append({"phase": "setup", "copyable": st.get("kind") == "cmd", "kind": st.get("kind"), "text": txt})
        seen.add(txt.strip())
    if run.get("command") and run["command"].strip() not in seen:
        steps.append({"phase": "start", "copyable": True, "kind": "cmd", "text": run["command"]})
    steps.append({"phase": "check", "copyable": True, "kind": "cmd", "text": "localhost check"})
    steps.append({"phase": "connect", "copyable": True, "kind": "cmd",
                  "text": "localhost connect opencode --engine %s" % eid})
    warn = []
    for g in eng.get("gotchas") or []:
        warn.append(g if isinstance(g, str) else json.dumps(g))
    for c in s.get("caveats") or []:
        warn.append(c if isinstance(c, str) else (c.get("text") or json.dumps(c)))
    payload = {"recipe": s["id"], "title": s.get("title"), "model": s.get("model"), "engine": eid,
               "repo": run.get("repo"), "requirements": s.get("requirements"), "steps": steps,
               "warnings": warn, "rule": "Run only copyable=true steps verbatim. Other steps are instructions, not commands."}
    lines = [s.get("title", s["id"]), "repo: %s" % run.get("repo"), ""]
    for i, st in enumerate(steps, 1):
        lines.append("%d. [%s] %s%s" % (i, st["phase"], "$ " if st["copyable"] else "", st["text"]))
    if warn:
        lines += ["", "Warnings:"] + ["- %s" % w[:300] for w in warn[:8]]
    out(args, payload, "\n".join(lines))


def cmd_check(args):
    from .check import check
    r = check(args.endpoint, args.model, max_tokens=args.max_tokens)
    if r["ok"]:
        text = "OK: %s answered at %s\nfirst token %.2fs, decode %s tok/s (%s)\nreply: %s" % (
            r["model"], r["endpoint"], r["time_to_first_token_s"], r["decode_tok_s"], r["token_count_source"],
            r["reply_preview"].replace("\n", " "))
    else:
        text = "NOT OK: %s" % r.get("error")
    out(args, r, text)
    return 0 if r["ok"] else 1


def cmd_connect(args):
    from .connect import OPENCODE_DEFAULT, merge_write, opencode_config
    from .detect import running_servers
    endpoint, model, engine = args.endpoint, args.model, args.engine
    if not endpoint:
        servers = running_servers()
        if not servers:
            out(args, {"ok": False, "error": "no local server running"},
                "No local model server is running. Start one (localhost guide <recipe>), or pass --endpoint.")
            return 1
        endpoint, engine = servers[0]["endpoint"], engine or servers[0]["engine_guess"]
        model = model or (servers[0]["models"] or [None])[0]
    if not model:
        out(args, {"ok": False, "error": "no model"}, "Pass --model (the server lists none).")
        return 1
    cfg, warnings = opencode_config(endpoint, model, context=args.context, engine=engine)
    payload = {"ok": True, "target": args.config or OPENCODE_DEFAULT, "config": cfg, "warnings": warnings,
               "written": False}
    if args.write:
        path, backup = merge_write(cfg, args.config or OPENCODE_DEFAULT)
        payload.update(written=True, target=path, backup=backup)
    text = json.dumps(cfg, indent=2)
    text += "\n\n" + ("Written to %s%s" % (payload["target"], " (backup: %s)" % payload.get("backup") if payload.get("backup") else "")
                      if payload["written"] else "Dry run. Add --write to merge this into %s" % payload["target"])
    text += "".join("\nWARNING: %s" % w for w in warnings)
    text += "\nThen run `opencode` and pick the model with /models."
    out(args, payload, text)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="localhost", description=__doc__.split("\n")[0], epilog=AGENT_NOTE)
    ap.add_argument("--version", action="version", version="localhost %s" % __version__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    common.add_argument("--data", help="dataset file (.json blob or saved site .html)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("data", parents=[common], help="where the dataset comes from, and its counts")
    p.add_argument("--refresh", action="store_true")
    p.set_defaults(fn=cmd_data)
    sub.add_parser("models", parents=[common], help="list model families").set_defaults(fn=cmd_models)
    p = sub.add_parser("recipes", parents=[common], help="list recipes, with filters")
    p.add_argument("--model"); p.add_argument("--hardware"); p.add_argument("--engine")
    p.add_argument("--runnable", action="store_true", help="only recipes with a copyable command")
    p.set_defaults(fn=cmd_recipes)
    p = sub.add_parser("show", parents=[common], help="one recipe, in full")
    p.add_argument("recipe"); p.set_defaults(fn=cmd_show)
    sub.add_parser("detect", parents=[common], help="read this machine's hardware").set_defaults(fn=cmd_detect)
    p = sub.add_parser("fit", parents=[common], help="which recipes fit this machine")
    p.add_argument("--model"); p.add_argument("--reserve", type=float)
    p.add_argument("--all", action="store_true", help="also list recipes that will not fit")
    p.add_argument("--no-detect", action="store_true", help="use only the flags below")
    for f, t in (("os", str), ("chip", str), ("gpu", str), ("gpus", int), ("ram", float), ("vram", float), ("device", str)):
        p.add_argument("--" + f, type=t)
    p.add_argument("--unified", choices=["unified", "separate"])
    p.set_defaults(fn=cmd_fit)
    p = sub.add_parser("guide", parents=[common], help="ordered setup steps for a recipe")
    p.add_argument("recipe"); p.set_defaults(fn=cmd_guide)
    p = sub.add_parser("check", parents=[common], help="test a running local server (cold prompt)")
    p.add_argument("--endpoint"); p.add_argument("--model"); p.add_argument("--max-tokens", type=int, default=48)
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("connect", parents=[common], help="point a UI at your local model")
    p.add_argument("ui", choices=["opencode"])
    p.add_argument("--endpoint"); p.add_argument("--model"); p.add_argument("--engine")
    p.add_argument("--context", type=int); p.add_argument("--config", help="config file path")
    p.add_argument("--write", action="store_true", help="merge into the config file (keeps a backup)")
    p.set_defaults(fn=cmd_connect)

    args = ap.parse_args(argv)
    try:
        rc = args.fn(args)
    except (DataError, KeyError, RuntimeError) as e:
        msg = e.args[0] if e.args else str(e)
        if getattr(args, "json", False):
            json.dump({"ok": False, "error": msg}, sys.stdout)
            sys.stdout.write("\n")
        else:
            sys.stderr.write("error: %s\n" % msg)
        return 2
    return rc or 0


if __name__ == "__main__":
    sys.exit(main())
