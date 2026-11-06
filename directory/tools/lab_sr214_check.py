#!/usr/bin/env python3
"""SR-214 acceptance check: every recipe page with lab data, in headless
Chromium. Asserts per page: renders the lab block, 0 console errors, 0
external (non file:/data:/blob:/same-origin) requests. Replay timing is
driven through DOM clicks only (app.js internals are not exposed). Writes a
JSON log + two screenshots to /home/orangepi/handover/sr126/.
Run with the Playwright venv python against a served site dir."""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = "/home/orangepi/.hermes/cache/scratch/qlr/directory"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8852/"
OUT = "/home/orangepi/handover/sr126"
os.makedirs(OUT, exist_ok=True)

DATA = json.load(open(os.path.join(ROOT, "data", "lab_results.json")))
LAB_IDS = sorted(DATA["models"].keys())
NULL_SPEED = sorted(sid for sid, m in DATA["models"].items() if not m.get("speed"))
MEASURED = sorted(sid for sid, m in DATA["models"].items() if m.get("speed"))
SETUP_IDS = [f[:-5] for f in os.listdir(os.path.join(ROOT, "data", "setups")) if f.endswith(".json") and not f.startswith("_")]
NONLAB = sorted(set(SETUP_IDS) - set(LAB_IDS))[0]

report = {"base": BASE, "lab_ids": len(LAB_IDS), "pages": [], "replay": {},
          "console_errors": [], "external_requests": [], "screenshots": [], "fails": []}

# pick the slowest measured recipe and its longest-word task so 1x is clearly
# partial after 6 s and 10x is clearly further along
sid = min(MEASURED, key=lambda s: DATA["models"][s]["speed"]["decode_tok_s"])
toks = DATA["models"][sid]["speed"]["decode_tok_s"]
task = max(DATA["models"][sid]["tasks"],
           key=lambda t: len(DATA["models"][sid]["tasks"][t]["answer"].split()))
nwords = len(DATA["models"][sid]["tasks"][task]["answer"].split())
full_chars = len(DATA["models"][sid]["tasks"][task]["answer"])


def classify(url):
    return url.startswith(("file:", "data:", "blob:"))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # --- 1) every lab recipe over http
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        cur_errs, cur_ext = [], []
        page.on("console", lambda m: cur_errs.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: cur_errs.append(str(e)))
        page.on("request", lambda r: cur_ext.append(r.url)
                if not (r.url.startswith(BASE.split("#")[0]) or classify(r.url)) else None)

        for sbid in LAB_IDS:
            cur_errs.clear(); cur_ext.clear()
            page.goto(BASE + "#/recipes/" + sbid)
            page.wait_for_timeout(350)
            has_block = page.locator(".lab-block").count()
            score = page.evaluate(
                "(document.querySelector('[data-lab-score]')||{}).getAttribute"
                " ? document.querySelector('[data-lab-score]').getAttribute('data-lab-score') : null")
            toks_attr = page.evaluate(
                "document.querySelector('[data-lab-toks]') ? "
                "document.querySelector('[data-lab-toks]').getAttribute('data-lab-toks') : null")
            nospeed = page.locator("[data-lab-nospeed]").count()
            tasks = page.locator(".lab-task").count()
            replay_btns = page.locator("[data-rep]").count()
            entry = {"id": sbid, "lab_block": has_block, "score": score, "toks": toks_attr,
                     "nospeed_line": nospeed, "tasks": tasks, "replay_btns": replay_btns,
                     "console_errors": list(cur_errs), "external": list(cur_ext)}
            report["pages"].append(entry)
            if has_block != 1:
                report["fails"].append(f"{sbid}: lab block count {has_block}")
            if tasks != 23:
                report["fails"].append(f"{sbid}: {tasks} task rows (want 23)")
            if cur_errs:
                report["console_errors"].append({sbid: cur_errs})
            if cur_ext:
                report["external_requests"].append({sbid: cur_ext})
            if sbid in NULL_SPEED and nospeed != 1:
                report["fails"].append(f"{sbid}: speed null but no 'No speed measured' line")
            if sbid in MEASURED and not toks_attr:
                report["fails"].append(f"{sbid}: speed measured but no tok/s shown")
        ctx.close()

        # --- 2) file:// pass: works offline, zero non-local requests
        fctx = browser.new_context(viewport={"width": 1280, "height": 900})
        fpage = fctx.new_page()
        ferrs, fext = [], []
        fpage.on("console", lambda m: ferrs.append(m.text) if m.type == "error" else None)
        fpage.on("pageerror", lambda e: ferrs.append(str(e)))
        fpage.on("request", lambda r: fext.append(r.url) if not classify(r.url) else None)
        fpage.goto("file://" + ROOT + "/site/index.html#/recipes/" + sid)
        fpage.wait_for_timeout(700)
        report["file_url"] = {"lab_block": fpage.locator(".lab-block").count(),
                              "console_errors": ferrs, "non_local_requests": fext}
        if ferrs or fext or fpage.locator(".lab-block").count() != 1:
            report["fails"].append("file:// pass: errors=%s external=%s block=%s" %
                                   (ferrs, fext, fpage.locator(".lab-block").count()))
        fctx.close()

        # --- 3) replay timing on the slowest measured recipe
        rctx = browser.new_context(viewport={"width": 1280, "height": 900})
        rp = rctx.new_page()
        rerrs = []
        rp.on("console", lambda m: rerrs.append(m.text) if m.type == "error" else None)
        rp.on("pageerror", lambda e: rerrs.append(str(e)))
        rp.goto(BASE + "#/recipes/" + sid)
        rp.wait_for_timeout(400)

        def q(sel):
            return rp.evaluate("document.querySelector(%r) ? "
                               "document.querySelector(%r).textContent : null" % (sel, sel))

        key = sid + "|" + task
        sel_ans = '[data-rep-ans="%s"]' % key
        sel_status = '[data-rep-status="%s"]' % key

        def open_task(tid, page=None):
            page = page or rp
            det = page.locator('.lab-task[data-lab-task="%s"]' % tid)
            if not det.evaluate("n => n.open"):
                det.locator("summary").click()
                page.wait_for_timeout(80)

        open_task(task)

        def set_rate(rate):
            rp.click('[data-rep-rate="%d"][data-rep-key="%s"]' % (rate, key))

        def reset_all():
            if rp.is_visible('[data-rep="reset"][data-rep-key="%s"]' % key):
                rp.click('[data-rep="reset"][data-rep-key="%s"]' % key)

        def measure(rate, seconds):
            reset_all()
            set_rate(rate)
            rp.click('[data-rep="start"][data-rep-key="%s"]' % key)
            time.sleep(seconds)
            chars = rp.evaluate("document.querySelector('%s').textContent.length" % sel_ans)
            status = q(sel_status)
            if rp.is_visible('[data-rep="pause"][data-rep-key="%s"]' % key):
                rp.click('[data-rep="pause"][data-rep-key="%s"]' % key)
            out = {"rate": rate, "seconds": seconds, "chars": chars, "status": status}
            set_rate(1)
            return out

        m1 = measure(1, 6)          # replay starts and emits text
        m1_s = measure(1, 2)        # same window as 10x below
        m10_s = measure(10, 2)      # 10x must out-emit 1x in the same 2 s
        m10_full = measure(10, 6)
        report["replay"] = {"recipe": sid, "tok_s": toks, "task": task,
                            "answer_words": nwords, "answer_full_chars": full_chars,
                            "1x_after_6s": m1, "1x_after_2s": m1_s, "10x_after_2s": m10_s,
                            "10x_after_6s": m10_full,
                            "console_errors": rerrs}
        if not m1["chars"]:
            report["fails"].append("replay 1x emitted nothing after 6s")
        if m10_s["chars"] <= m1_s["chars"]:
            report["fails"].append("replay 10x not faster than 1x over 2s: %s vs %s" %
                                   (m10_s["chars"], m1_s["chars"]))
        if full_chars and m1["chars"] >= full_chars:
            report["fails"].append("replay 1x already complete after 6s — pick a longer task")
        # mid-run screenshot (replay visibly typing)
        reset_all()
        rp.click('[data-rep="start"][data-rep-key="%s"]' % key)
        time.sleep(5)
        sh1 = os.path.join(OUT, "lab-replay-mid-run.png")
        rp.locator(".lab-block").screenshot(path=sh1)
        report["screenshots"].append(sh1)
        if rp.is_visible('[data-rep="pause"][data-rep-key="%s"]' % key):
            rp.click('[data-rep="pause"][data-rep-key="%s"]' % key)
        rctx.close()

        # --- 4) reduced motion: replay shows the full text immediately
        rmctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                    reduced_motion="reduce")
        rmp = rmctx.new_page()
        rmp.goto(BASE + "#/recipes/" + sid)
        rmp.wait_for_timeout(400)
        open_task(task, rmp)
        rmp.click('[data-rep="start"][data-rep-key="%s"]' % key)
        rmp.wait_for_timeout(250)
        rm_len = rmp.evaluate("document.querySelector('%s').textContent.length" % sel_ans)
        rm_status = rmp.evaluate("document.querySelector('%s') ? document.querySelector('%s').textContent : null"
                                 % (sel_status, sel_status))
        report["reduced_motion"] = {"chars": rm_len, "full": full_chars, "status": rm_status}
        if rm_len != full_chars:
            report["fails"].append("reduced motion did not show full text immediately")
        rmctx.close()

        # --- 5) speed=null recipe: static answers, replay disabled
        nctx = browser.new_context(viewport={"width": 1280, "height": 900})
        np_ = nctx.new_page()
        nerrs = []
        np_.on("console", lambda m: nerrs.append(m.text) if m.type == "error" else None)
        np_.on("pageerror", lambda e: nerrs.append(str(e)))
        nsid = NULL_SPEED[0]
        np_.goto(BASE + "#/recipes/" + nsid)
        np_.wait_for_timeout(400)
        report["nospeed_page"] = {
            "id": nsid,
            "replay_buttons": np_.locator("[data-rep]").count(),
            "disabled_lines": np_.locator(".lab-replay-off").count(),
            "score": np_.evaluate("document.querySelector('[data-lab-score]') ? "
                                  "document.querySelector('[data-lab-score]').getAttribute('data-lab-score') : null"),
            "console_errors": nerrs}
        if np_.locator("[data-rep]").count() != 0:
            report["fails"].append(f"{nsid}: replay buttons present despite speed null")
        if np_.locator(".lab-replay-off").count() != 23:
            report["fails"].append(f"{nsid}: {np_.locator('.lab-replay-off').count()} disabled lines (want 23)")
        sh2 = os.path.join(OUT, "lab-nospeed-recipe.png")
        np_.locator(".lab-block").screenshot(path=sh2)
        report["screenshots"].append(sh2)
        nctx.close()

        # --- 6) mobile viewport + a recipe WITHOUT lab data
        mctx = browser.new_context(viewport={"width": 390, "height": 780})
        mp = mctx.new_page()
        merrs = []
        mp.on("console", lambda m: merrs.append(m.text) if m.type == "error" else None)
        mp.on("pageerror", lambda e: merrs.append(str(e)))
        mp.goto(BASE + "#/recipes/" + sid)
        mp.wait_for_timeout(400)
        overflow = mp.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
        mp.goto(BASE + "#/recipes/" + NONLAB)
        mp.wait_for_timeout(400)
        report["mobile"] = {"overflow": bool(overflow), "console_errors": merrs,
                            "nonlab_id": NONLAB,
                            "nonlab_lab_block": mp.locator(".lab-block").count()}
        if mp.locator(".lab-block").count() != 0:
            report["fails"].append("non-lab recipe rendered a lab block")
        if merrs:
            report["fails"].append("mobile console errors: %s" % merrs)
        mctx.close()

        browser.close()

    with open(os.path.join(OUT, "lab_acceptance.json"), "w") as fh:
        json.dump(report, fh, indent=1, ensure_ascii=False)
    print(json.dumps({
        "pages_checked": len(report["pages"]),
        "total_console_errors": sum(len(p["console_errors"]) for p in report["pages"]),
        "total_external_requests": sum(len(p["external"]) for p in report["pages"]),
        "file_url": report["file_url"],
        "replay": report["replay"],
        "reduced_motion": report["reduced_motion"],
        "nospeed_page": report["nospeed_page"],
        "mobile": report["mobile"],
        "screenshots": report["screenshots"],
        "fails": report["fails"],
    }, indent=1))
    return 1 if report["fails"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
