# localhost: CLI spec (draft, 2026-10-12)

Status: v0.1 built on branch `localhost-cli` (not released). Decisions by Shuenrui on 2026-10-12, in Slack:
name **localhost**; UI approach **Option 1, connect existing UIs (OpenCode first)**; directory first,
then help users host.

## Goal
Any AI agent, or person, can go from "what is this machine?" to "a local model running, checked, and
open in a good UI", using only what the directory records.

## Users
1. AI agents (Claude Code, Codex, Hermes, Cursor) acting for a user. They need `--json`, no prompts,
   and no invented commands.
2. People in a terminal who want the same answers without browsing.

## Flow
`detect` → `fit` → `guide <recipe>` → (user or agent runs the copyable steps) → `check` → `connect opencode`

## v0.1 (built, tested on this box)
| Command | Does | Source of truth |
|---|---|---|
| `data` | dataset origin, date and counts; 24 h cache | the blob embedded in the live site |
| `models`, `recipes`, `show` | lookup with filters | same |
| `detect` | OS, CPU, RAM, GPU/VRAM (nvidia-smi, rocm-smi, Apple and APU rules), disk, installed engines, running servers | the machine |
| `fit` | groups every recipe: exact / similar / estimated / uncertain / unsupported | port of the site's `classify()`; parity-tested |
| `guide` | ordered steps, each flagged copyable or not | recipe `run.steps` and `run.command`, verbatim |
| `check` | live server test: first-token time, decode tok/s, cold prompt with a nonce | the running server |
| `connect opencode` | OpenCode provider config (dry run; `--write` merges and keeps a backup) | OpenCode provider docs |

Rules carried over from the site: never synthesise a command; say when data is missing; label method and provenance.

## Next (v0.2), in order
1. **Fix the fit reserve bug (site and CLI).** On a 24 GB card, Linux's 4 GB reserve marks recipes
   recorded at 24 GB as "will not fit", including the 4090 recipes measured on that very card.
2. **Engine install data.** Add an install block per engine to `data/engines/*.json`, sourced from each
   engine's docs, so `guide` can give a copyable install step.
3. **`run <recipe>`**: execute copyable steps after showing them, with explicit confirmation for each.
   `--dry-run` is the default.
4. **`report`**: after `check`, send a measurement (hardware, recipe, tok/s, method, nonce) to the repo
   as a GitHub issue or PR. Grows the data for small machines.
5. **MCP server mode** (`localhost mcp`): the same commands exposed as agent tools.
6. **`llms.txt` plus a JSON index** for agents that only browse.
7. More `connect` targets once OpenCode works end to end on real hardware.

## Non-goals
- Our own chat or coding UI (Option 3). Our own fork of OpenCode (Option 2) only if users ask for it.
- Running anything without the user's say-so.

## Open issues
- Site bug: hardware entries written as `{"id", "count"}` never match on the site. The CLI handles them.
  The fix belongs in `site_src/app.js`.
- Rebrand timing: the site and repo still say "Qwen Local-Run". Today's announcement copy may use the old
  name, so rename the site after that post, or update the copy first.
- Names: `localhost` is free on PyPI and Homebrew, and taken on npm (a file server) and GitHub (@localhost).
  Claim the PyPI name before announcing the CLI.
- Not yet tested end to end: OpenCode actually chatting with a local model. This box is CPU only, and
  OpenCode's long prompts would take minutes per turn here. Test on a GPU machine.
