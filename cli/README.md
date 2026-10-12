# localhost CLI (v0.1, preview)

Find, set up, check and connect local LLMs, using the localhost directory
(https://local.innstance.app/). Python 3.8+, no dependencies. Every command takes `--json`.

```
pip install ./cli            # from a clone of this repo (not on PyPI yet)
localhost detect             # what this machine has: GPU, VRAM, RAM, engines, running servers
localhost fit                # which recipes fit this machine (same logic as the site's My Hardware page)
localhost guide <recipe-id>  # ordered setup steps, copied from the recipe; never invented
localhost check              # test the running local server: cold prompt, first-token time, decode tok/s
localhost connect opencode   # point OpenCode at your local model (dry run; --write to apply)
```

Lookup: `localhost models`, `localhost recipes --model M --hardware H --engine E --runnable`,
`localhost show <recipe-id>` (prefixes work), `localhost data --refresh`.

## For AI agents

1. `localhost detect --json`. Don't ask the user for specs you can read.
2. `localhost fit --json` (add `--model <id>` to narrow). Prefer `exact`, then `similar`, then `estimated`.
   Treat `uncertain` and `unsupported` as "do not attempt" unless the user insists.
3. `localhost guide <id> --json`. Run only steps with `"copyable": true`, verbatim. The rest are
   instructions. The directory records no engine install commands, so follow the engine's linked docs.
4. `localhost check --json` once the server is up.
5. `localhost connect opencode --json`, then `--write` once the user agrees.

## Where the data comes from

The CLI reads the same JSON blob the site embeds, so the two cannot disagree. It is cached at
`~/.cache/localhost/data.json` for 24 h. Overrides: `--data FILE` or `$LOCALHOST_DATA`, and
`$LOCALHOST_SITE` to point at another copy of the site.

## Tests

`python3 tests/test_fit_parity.py` runs the site's own `classify()` (pulled from `site_src/app.js`,
run in node) next to the CLI's port, over 9 machine profiles × 83 recipes. Expected result: all match,
except one documented divergence. Recipes that list hardware as `{"id": ..., "count": N}` never match on
the site (a site bug). The CLI matches them when the machine has at least N devices.
