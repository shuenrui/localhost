#!/usr/bin/env python3
"""SR-126 v0 data layer: build the lab-results blob for the directory.

Reads retired measured data ONLY (quality suite v2 + box bench results),
never anything unreleased:
  - <repo>/data/quality2/scores.json          totals, per-task scores, cats
  - <repo>/data/quality2/raw_*.jsonl          answers (content only; NO thinking)
  - <qres>/*.bench.json                       measured decode tok/s + ttft per run
Output: <dir>/data/lab_results.json  (consumed later by build.py; not yet embedded)

Answers kept: one per (model, task) — the seed-1 row, first non-empty content.
Rule per task id: only tasks NOT in scores.void. A row with error set or empty
content still ships (the site shows "no answer" honestly); we never synthesise.
"""
import json, glob, os, re, statistics, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DIRECTORY = os.path.dirname(HERE)          # .../directory
DATA = os.path.join(DIRECTORY, "data")

LABREPO = os.path.expanduser("~/spark-lab-repo/data")
Q2 = os.path.join(LABREPO, "quality2")
QRES = os.path.expanduser("~/spark-lab-data/queue/results")

def median(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and x > 0]
    return round(statistics.median(xs), 2) if xs else None

def setup_files():
    return {os.path.splitext(f)[0] for f in os.listdir(os.path.join(DATA, "setups"))}

def main():
    scores = json.load(open(os.path.join(Q2, "scores.json"), encoding="utf-8"))
    max_total = scores["max_total"]
    void = set(scores.get("void") or [])
    suite_date = (scores.get("updated") or "")[:10]

    manual = {k: v for k, v in json.load(open(os.path.join(DATA, "lab_view_map.json"), encoding="utf-8")).items()
              if not k.startswith("_")}

    setups = setup_files()
    # map lab label -> setup id: manual entry, exact file, or ':' -> '-' (ollama tag)
    out_models, gaps = {}, []
    for label, rec in sorted(scores["models"].items()):
        sid = manual.get(label)
        if sid is None and label in setups:
            sid = label
        if sid is None:
            cand = [s for s in setups if s == label.replace(":", "-")]
            sid = cand[0] if cand else None
        if sid is None or sid not in setups:
            gaps.append(label)
            continue

        # answers: seed-1 rows, content only (raw file names use _ where labels use :)
        tasks = {}
        for fn in (label, label.replace(":", "_")):
            if tasks: break
            rawp = os.path.join(Q2, f"raw_{fn}.jsonl")
            if not os.path.exists(rawp):
                continue
            for line in open(rawp, encoding="utf-8", errors="replace"):
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if int(r.get("seed") or 0) != 1:
                    continue
                t = r.get("task")
                if not t or t in void or t in tasks:
                    continue
                tasks[t] = {
                    "score": rec["per_task"].get(t),
                    "answer": r.get("content") or "",
                    "done": r.get("done_reason") or ("error" if r.get("error") else ""),
                    "wall_s": r.get("wall_s"),
                    "engine": r.get("engine") or "",
                }

        # speed: median across all runs of the bench file
        # (bench files are named by lab label OR by setup id — try both)
        speed = None
        bp = os.path.join(QRES, f"{label}.bench.json")
        if not os.path.exists(bp):
            alt = glob.glob(os.path.join(QRES, f"{label}*.bench.json")) \
                  or glob.glob(os.path.join(QRES, f"{sid}*.bench.json"))
            bp = alt[0] if alt else None
        if bp:
            try:
                b = json.load(open(bp, encoding="utf-8"))
                runs = b.get("runs") or []
                speed = {
                    "decode_tok_s": median([x.get("decode_tok_s") for x in runs]),
                    "ttft_ms": median([x.get("ttft_s", 0) * 1000 for x in runs if x.get("ttft_s") is not None]),
                    "n": len(runs),
                    "date": (b.get("date") or "")[:10],
                    "file": os.path.basename(bp),
                }
            except Exception as e:
                speed = {"error": str(e)[:100]}

        out_models[sid] = {
            "label": label,
            "total": rec["total"],
            "all3": rec.get("all3"),
            "cats": rec.get("cats"),
            "n_tasks": len(tasks),
            "tasks": tasks,
            "speed": speed,
        }

    # honest rank among the models IN this blob
    order = sorted(out_models.items(), key=lambda kv: -kv[1]["total"])
    for i, (sid, m) in enumerate(order, 1):
        m["rank"] = i

    blob = {
        "generated": datetime.date.today().isoformat(),
        "suite": {"name": "quality v2", "status": "retired", "max_total": max_total,
                  "void": sorted(void), "date": suite_date,
                  "method": "24 hard tasks, n=3 seeds, rule-scored, answers = seed 1"},
        "models": out_models,
        "gaps_no_page": gaps,
    }
    outp = os.path.join(DATA, "lab_results.json")
    tmp = outp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(blob, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, outp)

    raw = os.path.getsize(outp)
    print(f"models={len(out_models)} with_answers={sum(1 for m in out_models.values() if m['n_tasks'])}"
          f" with_speed={sum(1 for m in out_models.values() if m.get('speed'))}"
          f" gaps_no_page={len(gaps)}")
    print(f"blob={raw/1e6:.2f} MB  ->  live 1.15 MB + this")
    print("gap labels:", ", ".join(gaps) if gaps else "(none)")
    top = order[:3]
    for sid, m in top:
        sp = (m.get("speed") or {}).get("decode_tok_s")
        print(f"  #{m['rank']} {sid}: {m['total']}/{max_total} @ {sp} tok/s")

if __name__ == "__main__":
    main()
