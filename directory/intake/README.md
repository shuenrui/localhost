# Intake record (written by the Radar -> directory intake, daily ~11:30 KL)

Every decision the intake makes, so "what happened to model X / that number / that command" has one answer.
The directory itself (`../data/`) stays the source of truth for what is published; this folder is the audit trail.

- `decisions.json`  every Hugging Face repo the Radar surfaced: add / skip / review, with the reason
- `numbers.json`    every speed number from a post: imported onto a recipe, held, or dropped (and why)
- `social_recipes.json` every run command copied from a post: imported, held, or dropped (and why)
- `spark_tests.json` recipes sent to the DGX Spark, with result status
- `review.json`     what needs a human call: unknown engines, unmatched hardware, missing file sizes,
                    model links not on Hugging Face, repos flagged "review"
Held items are retried daily for 14 days, then dropped. Approving a new engine = adding it to `../data/engines/`.
