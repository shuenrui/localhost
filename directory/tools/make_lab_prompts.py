#!/usr/bin/env python3
"""SR-214: extract the frozen quality-v2 task prompts for the site build.

Reads the retired lab suite definition ONLY:
  - <repo>/data/quality_tasks_v2.json   (version, frozen date, 24 tasks)
and writes directory/data/lab_prompts.json:

  {"version": "quality-v2", "frozen": "...", "max_total": 23, "void": ["L6"],
   "tasks": [{"id": "H1", "cat": "code", "prompt": "..."}, ...]}

Rules enforced here (the acceptance gate for SR-214 data):
  * only the PROMPT TEXT (plus id/cat) ships — never scoring code/tests,
    never anything from quality v3 or battle prompts;
  * voided tasks (suite "void", e.g. L6) are dropped: 24 defined -> 23 ship;
  * every task id referenced by data/lab_results.json appears here;
  * the suite is the retired v2 set: the script refuses to read any other
    quality_tasks_*.json file.
Stdlib only; run from anywhere: python3 directory/tools/make_lab_prompts.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
SRC = os.path.expanduser("~/spark-lab-repo/data/quality_tasks_v2.json")


def main() -> int:
    if not os.path.exists(SRC):
        print(f"FAIL: missing {SRC}", file=sys.stderr)
        return 1
    with open(SRC, encoding="utf-8") as fh:
        suite = json.load(fh)
    if suite.get("version") != "quality-v2":
        print(f"FAIL: unexpected suite version {suite.get('version')!r}", file=sys.stderr)
        return 1

    void = sorted(suite.get("void") or [])
    blob_path = os.path.join(DATA, "lab_results.json")
    blob = None
    if os.path.exists(blob_path):
        with open(blob_path, encoding="utf-8") as fh:
            blob = json.load(fh)
        void = sorted(set((blob.get("suite") or {}).get("void") or []) | set(void))

    tasks = []
    for t in suite["tasks"]:
        if t["id"] in void:
            continue
        tasks.append({"id": t["id"], "cat": t["cat"], "prompt": t["prompt"]})
    ids = {t["id"] for t in tasks}

    if blob is not None:
        used = set()
        for m in blob["models"].values():
            used.update(m["tasks"].keys())
        missing = sorted(used - ids)
        if missing:
            print(f"FAIL: lab_results task ids not in shipped prompts: {missing}", file=sys.stderr)
            return 1

    out = {
        "version": suite["version"],
        "frozen": suite.get("frozen"),
        "runs": suite.get("runs"),
        "void": void,
        "tasks": sorted(tasks, key=lambda t: t["id"]),
    }
    tmp = os.path.join(DATA, "lab_prompts.json") + ".tmp"
    out_path = os.path.join(DATA, "lab_prompts.json")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, out_path)
    print(f"wrote {out_path}: {len(tasks)} tasks, "
          f"{os.path.getsize(out_path):,} bytes (void: {out['void']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
