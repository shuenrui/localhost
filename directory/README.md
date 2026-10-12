# localhost (formerly the Qwen Local-Run Directory)

A data-driven directory of every community way to run a Qwen model on hardware
you own. It scales the hand-written dashboard at `local.innstance.app`
from a single shelf to hundreds of filterable entries without hand-editing HTML.

[Open the live directory](https://local.innstance.app/) or read the
[repository overview](../README.md) for a visitor-focused tour.

The unit of an entry is a **runnable setup**: one specific checkpoint, one
specific engine configuration, on specific hardware. That is the thing that
actually gets run and actually gets measured, so it is the thing the directory
stores. A model with 8 checkpoints across 3 engines is 24 setups, not one row.

## Layout

```
directory/
├── SCHEMA.md            the data-model contract (read this before adding data)
├── validate.py          stdlib validator; fails the build on bad data
├── build.py             stdlib generator -> site/index.html (self-contained)
├── site_src/            the page source, inlined by build.py
│   ├── shell.html            skeleton with __CSS__/__DATA__/__APP__ slots
│   ├── app.css               design system, layouts, breakpoints, both themes
│   └── app.js                hash router, four tabs, filters, compare, hardware
├── verify_browser.py    headless-Chromium checks against the built site
├── data/
│   ├── models/<id>.json      architecture, context, modalities, license
│   ├── hardware/<id>.json    the box: memory, bandwidth, arch
│   ├── engines/<id>.json     the server: SGLang, vLLM, llama.cpp, ...
│   ├── publishers.json       who made things: labs, quant shops, individuals
│   └── setups/<id>.json      one runnable setup  <- the main entity
└── site/index.html      generated; commit or serve it, do not edit it
```

The site is four tabs behind one self-contained file: **Models** at `#/`
(model-first browsing with curated practical minimums), **Recipes** at
`#/recipes` (the complete advanced index, with no personalization gate), **My
Hardware** at `#/hardware`, and **Compare** at `#/compare`. Recipes, model
families and publishers have permanent URLs at `#/recipes/<id>`,
`#/models/<id>` and `#/publishers/<id>`. Routing is hash-based because `ifhost
publish` serves exactly one file at `/`; the design rationale is in
[`docs/redesign-2026-09-10/`](../docs/redesign-2026-09-10/).

## Workflow

```bash
# Run once on a new checkout.
bash directory/tools/install_verify_env.sh

# After editing or adding data/setups/<id>.json:
python3 directory/check.sh
```

The gate validates the data, fetches every cited URL, rebuilds the site, and
runs the browser suite against a local server. It exits non-zero if any stage
fails. `build.py` also runs `validate.py` itself and refuses to write on
failure. The generated page is a single self-contained HTML file: the dataset
is inlined as JSON, so it can be served statically or opened from disk with no
build step.

## Provenance is the load-bearing rule

Every number carries a `provenance` field and the site never mixes tiers:

| Tag      | Meaning                                    | Trust |
|----------|--------------------------------------------|-------|
| `box`    | measured on our own hardware, method stated | high  |
| `forum`  | reported by a community builder, linked     | mid   |
| `vendor` | claimed by the publisher of the artifact    | low   |

`box` numbers must have `date`, `n`, and `method`. `forum` and `vendor` numbers
must have a `source` URL. A number with no source is a validation error, and the
fix is to delete the number, not to downgrade the rule. A setup's
`provenance_tier` may never overstate its best measurement, and the validator
enforces that.

## Current coverage

83 setups, 22 model families, 10 hardware classes, 8 engines, and 36 publishers.
Eight model families currently have a curated practical baseline; fourteen are
shown as `Not verified yet` rather than receiving an estimated requirement.
Model families span the 3.0, 3.5, 3.6, and 3.8 lines including VL and Omni.

Community entries came from three research passes (HuggingFace quant cards,
GitHub run recipes, forum threads); every candidate was re-checked against the
validator's enums and every URL re-fetched before merging. A fourth pass
(social channels: X, YouTube, Reddit, GitHub discussions, vendor forums) is
governed by AGENTS laws 9–11 and collected with `tools/social_candidates.py`.
Reddit hard-403s this environment, so per the owner's mirror-accepted decision
(2026-09-10) Reddit-sourced numbers enter only via a pullpush/arctic-shift
mirror recorded in `mirror_url`, with the quote lifted from the mirror
payload; `check_links.py` verifies the mirror.

**Installing a recipe:** see [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) for
the host details to collect, how to read recipe evidence, and the reviewed
status of the 40 recipes that lacked copyable commands in the October 2026
audit. It distinguishes verified commands from GUI steps and incomplete or
conflicting upstream instructions.

Scope of the family list, from an audit of the Qwen org on HuggingFace:
there is **no Qwen 4 series** — 3.8 is the newest line. Deliberately excluded
from setups: `Qwen3.8-2.4T-A95B` and `Qwen3-Coder-480B-A35B` (cluster-scale, no
single-box local lane), sub-4B edge models (no hardware class below a 24 GB GPU
or 32 GB Mac exists yet), and the Embedding/Reranker/ASR/TTS families (not
text-generation serving). Vision and Omni families are included where a local
lane exists.

## Known gaps, deliberately

- `hardware/gpu-24gb.json` and `hardware/mac-128gb.json` are **class** entries
  (RTX 3090/4090 class; M3/M4 Max class), not single SKUs, and are not measured
  by us. They carry a bandwidth range and a note saying so.
- `engines/custom-fork.json` has a null `url` on purpose: it is a category for
  builder-specific forks with no single canonical upstream. The validator
  accepts a null URL only for `kind: "fork"`.
- Community research (HuggingFace quants, GitHub recipes, forum-reported
  numbers) is merged as of 2026-09-05; the social-channels pass (law 9–11,
  `tools/history/inputs/pass4-social/`) is collected but unmerged pending
  owner review. What remains uncovered: Mac lanes for the 27B dense
  model beyond MLX/llama.cpp defaults, and any true fine-tunes — everything
  here so far is a quant, a build, or a weight-edited derivative.
- `bench/` results are not wired in yet. Once they are, `box` rows should be
  regenerated from `measurements.jsonl` rather than typed by hand.

## Bench wiring

`box` rows are not typed by hand once the harness has run them. `bench/ab.py`
writes `results/<exp>-<stamp>/results.json`; `import_bench.py` turns those rows
into measurements on the matching setup:

    python3 directory/import_bench.py bench/results/<exp>-<stamp> --engine mtp          # dry run
    python3 directory/import_bench.py bench/results/<exp>-<stamp> --engine mtp --apply  # write

`directory/data/bench_map.json` maps `<experiment model name>@<engine>` to a
setup id; `--engine` is required when a model has several lanes because
`results.json` does not record which engine the run used. Applying replaces
only the `box` measurements for the touched metrics (forum/vendor rows are
never touched), flips the setup to `measured`, and appends an audit line per
measurement to `data/measurements.jsonl`. Running the benchmarks themselves
still needs a booted model, which is a separate decision.

## Verification

`verify_browser.py` drives the built page in headless Chromium (real clicks,
typing, selection and navigation) and runs ~170 behavioural checks: every route
resolving and an unknown route rendering a 404; the first-viewport contract; all
65 recipes rendering with no filter and no profile; shelf headers carrying every
required field with `not recorded` where the data is null; the single-stream
headline rule recomputed against the raw dataset for every row; the four
confidence dimensions recomputed cell by cell; every filter option checked
against the inlined data; all nine sort modes and the non-dismissible speed
disclosure; expand/collapse by mouse and keyboard; the copy button and clipboard
contents, and prose steps carrying no copy affordance; the compare rail's absence
at zero, its four-recipe cap, cross-tab persistence, the seven workspace
sections, incomparability detection and the absence of any winner marker; My
Hardware's five groups, the full memory breakdown, the KV line being derived only
where bytes-per-token is recorded, and the absence of any unconditional "fits"
verdict anywhere; detection degrading honestly with the APIs stubbed out; blocked
site storage not breaking the page; zero network requests after load; landmarks,
heading order, accessible names, live regions and reduced motion; entity leakage;
and horizontal overflow at 320, 390, 834, 1440 and 1920 in both themes. It exits
non-zero on any failure. See its docstring for the Playwright setup, and
`docs/redesign-2026-09-10/08-implementation-and-verification.md` for the
check-by-check mapping from the previous suite. Pass a URL as the first argument
to verify a deployed copy:

    directory/tools/.pwenv/bin/python directory/verify_browser.py https://local.innstance.app/

## Live

Live at **https://local.innstance.app/**, a static Innstance site owned by the Pro account
`shuenrui0003@gmail.com`. Publishing replaces the whole site:

    innstance publish --name local directory/site/index.html

(`ifhost` is the same binary under its old name.) The old address local.host.impossibuild.ai now
redirects here. After publishing, fetch the page with a cache-buster and compare the bytes with the
build.

## Repository

Canonical home: **https://github.com/shuenrui/localhost** (renamed from `qwen-local-run` on 2026-10-12; old links redirect) (branch `main`,
pushed from this box's `qwen-directory-standalone` branch). The history starts
with this project; it contains no commits from any other repository. The
serving and benchmarking stack this directory measures against lives in a
local checkout of the public `MiaAI-Lab/Qwen3.8-27B-SGLang-DGX-Spark` repo and
is credited where its numbers appear, but is not an upstream of this project.
