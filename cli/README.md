# localhost CLI (v0.2, preview)

Find, set up, check and connect local LLMs, using the localhost directory
(https://local.innstance.app/). Python 3.8+, no dependencies. Every command takes `--json`.

```
pip install "git+https://github.com/shuenrui/localhost.git#subdirectory=cli"

localhost detect             # what this machine has: GPU, VRAM, RAM, engines, running servers
localhost fit                # which recipes fit this machine (same logic as the site's My Hardware page)
localhost guide <recipe-id>  # ordered steps: engine install (official docs), setup, start; never invented
localhost run <recipe-id>    # walk those steps in a terminal, asking before every command
localhost check              # test the running local server: cold prompt, first-token time, decode tok/s
localhost connect opencode   # point OpenCode at your local model (dry run; --write to apply, keeps a backup)
localhost report             # measure the running model and get a prefilled GitHub issue to contribute it
localhost mcp                # run as an MCP server (stdio) so agents get these as tools
```

Lookup: `localhost models`, `localhost recipes --model M --hardware H --engine E --runnable`,
`localhost show <recipe-id>` (prefixes work), `localhost data --refresh`.

## For AI agents

1. `localhost detect --json`. Don't ask the user for specs you can read.
2. `localhost fit --json` (add `--model <id>` to narrow). Prefer `exact`, then `similar`, then `estimated`.
   Treat `uncertain` and `unsupported` as "do not attempt" unless the user insists.
3. `localhost guide <id> --json`. Run only steps with `"copyable": true`, verbatim. The rest are
   instructions or notes. Install steps come from each engine's official install page, with the URL recorded.
4. `localhost run <id>` is for a person at a terminal. An agent should only pass `--yes` after the user
   has agreed to every step it prints.
5. `localhost check --json` once the server is up, then `localhost connect opencode --json`, and `--write`
   once the user agrees.

MCP: add `{"command": "localhost", "args": ["mcp"]}` to your client's MCP servers. Its tools are
`detect`, `fit`, `guide`, `show`, `recipes`, `models` and `check`, all read-only. `check` sends one test prompt.

## How fit works (same rules as the site)

- Unified memory (Mac, Strix Halo, GB10): the OS safety reserve (macOS 6 GB, Linux 4 GB, Windows 8 GB)
  comes off the shared pool.
- Discrete GPU: VRAM is compared with the recipe's recorded resident figure as-is, because that figure was
  measured on that size of card. The reserve comes off system RAM only. A recipe within 1 GB of the card's
  size is flagged "Tight".
- Offload recipes (needs more than the card, records a lower `min_vram_gb`): need VRAM >= `min_vram_gb` and
  VRAM + usable RAM >= `memory_gb`.
- Recipes recorded on N devices (`{"id": ..., "count": N}`) count as "similar hardware" only on a machine
  with at least N GPUs.

## Where the data comes from

The CLI reads the same JSON blob the site embeds, so the two cannot disagree. It is cached at
`~/.cache/localhost/data.json` for 24 h. Overrides: `--data FILE` or `$LOCALHOST_DATA`, and
`$LOCALHOST_SITE` to point at another copy of the site.

## Tests

- `python3 tests/test_fit_parity.py` pulls the site's own fit functions out of `site_src/app.js`, runs them
  in node, and compares them with the CLI over 13 machine profiles × 83 recipes. Expected result: all match.
- `python3 tests/test_fit_cases.py` checks the behaviour: 24 GB recipes fit 24 GB cards, offload counts RAM,
  multi-GPU recipes need that many GPUs, and the Tight note appears.
