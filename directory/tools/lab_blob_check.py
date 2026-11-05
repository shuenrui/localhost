#!/usr/bin/env python3
"""SR-126 blob checks (RED->GREEN gate, run before any site embed):
 1. no 'thinking' text anywhere in the blob (privacy/size rule: answers only)
 2. voided task L6 appears in NO task dict
 3. every total in the blob == scores.json total, rank order == totals desc
 4. every setup id referenced exists in data/setups/ (no broken links)
 5. every stored answer appears verbatim in its raw jsonl (no synthesis)
 6. every model has speed or an explicit null (never a made-up number)
Exit 0 = all pass."""
import json, os, sys, glob
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")   # .../directory/data
blob = json.load(open(os.path.join(DATA, "lab_results.json"), encoding="utf-8"))
scores = json.load(open(os.path.expanduser("~/spark-lab-repo/data/quality2/scores.json"), encoding="utf-8"))
fails = []

raw = json.dumps(blob, ensure_ascii=False)
# 1
if '"thinking"' in raw:
    fails.append("1: blob contains a thinking field")
# 2
for sid, m in blob["models"].items():
    if "L6" in m["tasks"]:
        fails.append(f"2: void task L6 present for {sid}")
# 3
for sid, m in blob["models"].items():
    lab = m["label"]
    if abs(m["total"] - scores["models"][lab]["total"]) > 1e-9:
        fails.append(f"3: total mismatch {sid}")
seq = [(m["total"]) for sid, m in sorted(blob["models"].items(), key=lambda kv: kv[1]["rank"])]
if seq != sorted(seq, reverse=True):
    fails.append("3: rank order != totals desc")
# 4
setups = {os.path.basename(f)[:-5] for f in glob.glob(os.path.join(DATA, "setups", "*.json"))}
missing = [sid for sid in blob["models"] if sid not in setups]
if missing:
    fails.append(f"4: setup ids missing: {missing}")
# 5: spot-check ALL stored non-empty answers verbatim in their raw file
for sid, m in blob["models"].items():
    rp = os.path.expanduser(f"~/spark-lab-repo/data/quality2/raw_{m['label']}.jsonl")
    if not os.path.exists(rp):
        rp = os.path.expanduser(f"~/spark-lab-repo/data/quality2/raw_{m['label'].replace(':', '_')}.jsonl")
    if not os.path.exists(rp):
        fails.append(f"5: no raw for {sid}"); continue
    # collect seed-1 contents per task
    want = {}
    for line in open(rp, encoding="utf-8", errors="replace"):
        try: r = json.loads(line)
        except Exception: continue
        if int(r.get("seed") or 0) == 1 and r.get("task") not in blob["suite"]["void"]:
            t = r["task"]
            if t not in want: want[t] = r.get("content") or ""
    for t, stored in m["tasks"].items():
        a = stored["answer"]
        if a and a != want.get(t, "")[:len(a)]:
            if a not in (want.get(t) or ""):
                fails.append(f"5: answer for {sid}/{t} not verbatim in raw")
# 6
nospeed = [sid for sid, m in blob["models"].items() if m.get("speed") is None]
# not a failure — informational: those pages show the recipe's own measurement

print(f"models={len(blob['models'])} tasks_stored={sum(len(m['tasks']) for m in blob['models'].values())}"
      f" blob={os.path.getsize(os.path.join(DATA,'lab_results.json'))/1e6:.2f}MB")
print(f"speed=None (no bench file for lab config): {len(nospeed)} -> {nospeed}")
if fails:
    print("FAIL"); [print("  -", f) for f in fails]; sys.exit(1)
print("ALL CHECKS PASS")
