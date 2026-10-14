"""Build the ordered setup plan for one recipe. Shared by `guide`, `run` and the MCP server.

Every step is copied from the data: the engine's `install` block (from its official docs),
then the recipe's `run.steps` and `run.command`. Nothing is synthesised. A step is
`copyable` only when the data marks it as a literal command.
"""
import json
import platform

PLATFORM = {"darwin": "macos"}.get(platform.system().lower(), platform.system().lower())


def build(d, s, os_name=None):
    os_name = os_name or PLATFORM
    eid = d.engine_id(s)
    eng = d.engines.get(eid) or {}
    e_in = s.get("engine") if isinstance(s.get("engine"), dict) else {}
    run = s.get("run") or {}
    steps = []
    ins = eng.get("install") or {}
    methods = [m for m in ins.get("methods") or [] if os_name in (m.get("platforms") or [])]
    if e_in.get("bundled"):
        steps.append({"phase": "install", "copyable": False, "kind": "note",
                      "text": "No separate engine install: this tool bundles its own copy of %s." % eng.get("name", eid)})
    elif methods:
        m = methods[0]
        for st in m.get("steps") or []:
            steps.append({"phase": "install", "copyable": st.get("kind") == "cmd", "kind": st.get("kind"),
                          "text": st.get("text"), "method": m.get("label")})
        for alt in methods[1:]:
            steps.append({"phase": "install", "copyable": False, "kind": "note",
                          "text": "Alternative (%s): %s" % (alt.get("label"), " && ".join(
                              x.get("text") for x in alt.get("steps") or [] if x.get("kind") == "cmd") or
                              "; ".join(x.get("text") for x in alt.get("steps") or []))})
        for note in [m.get("note"), ins.get("note")]:
            if note:
                steps.append({"phase": "install", "copyable": False, "kind": "note", "text": note})
    else:
        steps.append({"phase": "install", "copyable": False, "kind": "do",
                      "text": "Install %s. The directory records no install method for %s; use the engine's own "
                              "instructions: %s" % (eng.get("name", eid), os_name, eng.get("url") or "(no link recorded)")})
    if e_in.get("requires_fork"):
        steps.append({"phase": "install", "copyable": False, "kind": "note",
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
    if not run.get("command") and not any(x["phase"] == "setup" and x["copyable"] for x in steps):
        steps.append({"phase": "start", "copyable": False, "kind": "note",
                      "text": "No launch command is recorded for this recipe. Follow the repository: %s" % run.get("repo")})
    if not e_in.get("bundled"):  # bundled tools expose no OpenAI-compatible server to check or connect
        steps.append({"phase": "check", "copyable": True, "kind": "cmd", "text": "localhost check"})
        steps.append({"phase": "connect", "copyable": True, "kind": "cmd", "text": "localhost connect opencode --engine %s" % eid})
    for i, st in enumerate(steps, 1):
        st["n"] = i
    # A bundled engine is the tool's own copy: the standalone engine's gotchas and install page do not apply.
    warn = [] if e_in.get("bundled") else [g if isinstance(g, str) else json.dumps(g) for g in eng.get("gotchas") or []]
    warn += [c if isinstance(c, str) else (c.get("text") or json.dumps(c)) for c in s.get("caveats") or []]
    return {"recipe": s["id"], "title": s.get("title"), "model": s.get("model"), "engine": eid, "os": os_name,
            "repo": run.get("repo"), "requirements": s.get("requirements"), "steps": steps, "warnings": warn,
            "install_source": None if e_in.get("bundled") else ins.get("source"),
            "rule": "Run only copyable=true steps, verbatim. Other steps are instructions or notes, not commands."}
