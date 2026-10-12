# localhost: CLI spec (2026-10-12)

Decisions by Shuenrui (Slack, 2026-10-12): the product is named **localhost**. UI approach is
**Option 1**: connect existing UIs, starting with OpenCode. Order: directory first, then help users
host. He gave full authority to finish the work.

## Goal
Any AI agent, or person, can go from "what is this machine?" to "a local model running, checked, and
open in a good UI", using only what the directory records.

## Users
1. AI agents (Claude Code, Codex, Hermes, Cursor) acting for a user. They need `--json` or MCP, no prompts,
   and no invented commands.
2. People in a terminal.

## Flow
`detect` → `fit` → `guide` / `run` → `check` → `connect opencode` → `report`

## Built (v0.2)
| Command | Does | Source of truth |
|---|---|---|
| `data`, `models`, `recipes`, `show` | lookup | the blob embedded in the live site (24 h cache) |
| `detect` | OS, CPU, RAM, GPU/VRAM, memory layout, disk, engines, running servers | the machine |
| `fit` | exact / similar / estimated / uncertain / unsupported | port of the site's `classify()` + `memFit()`; parity-tested (1079/1079) |
| `guide` | ordered steps for this OS, each flagged copyable | `engines/<id>.install` (official docs) + recipe `run` |
| `run` | walks the guide; asks before each command; stops on failure; `--from-step` resumes | same |
| `check` | cold-prompt test (nonce), first-token time, decode tok/s | the running server |
| `connect opencode` | OpenCode provider config; dry run, or `--write` (merge + backup) | OpenCode provider docs |
| `report` | measures, then prints a prefilled GitHub issue link (nothing is sent automatically) | `check` + `detect` |
| `mcp` | stdio MCP server; read-only tools | all of the above |

## Fixed on the site in the same change
- Fit: the OS reserve no longer comes off dedicated VRAM, so 24 GB recipes fit 24 GB cards (flagged Tight).
  Offload recipes now count system RAM.
- Fit: multi-GPU recipes match only machines with that many GPUs. Before, a 1-GPU machine was told a 2× 5090
  recipe was "verified on similar hardware".
- Quick start: "Step 0: install the engine", copied from the engine's official install page, with the link
  and retrieval date.
- Agents: a plain-HTML brief with every recipe and its JSON link, shown only without JavaScript. Plus
  `llms.txt` at the repo root.
- Rebrand: site, repo (`shuenrui/qwen-local-run` → `shuenrui/localhost`, old URLs redirect) and docs.

## Next
1. Test OpenCode end to end against a local model on a GPU machine. This box is CPU only.
2. More `connect` targets if users ask, starting with Open WebUI.
3. A triage label and template for `report` issues.
4. `llms.txt` served from the site itself. Needs a multi-file host; the static publish serves one file.
5. Publish the CLI to PyPI as `localhost` (the name is free as of 2026-10-12).

## Non-goals
- Our own chat or coding UI (Option 3). Our own fork of OpenCode (Option 2) only if users ask for it.
- Running anything without the user's say-so. MCP tools are read-only.
