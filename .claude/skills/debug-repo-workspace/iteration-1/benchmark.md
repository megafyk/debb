# debug-repo — iteration 1 benchmark

Results from running each of the 4 evals directly against the skill's helper
script (subagent runs hit Bash permission restrictions and stalled, so the
final iteration was driven by the parent session — outputs and grading still
live in this workspace).

## Per-eval pass rate

| Eval | Operation | Passed |
|---|---|---|
| `eval-0-register-payments-api` | register | 9 / 9 |
| `eval-1-list-registered-repos` | list (2 repos) | 5 / 5 |
| `eval-2-update-add-prometheus-source` | update (preserve siblings) | 7 / 7 |
| `eval-3-delete-with-confirmation` | delete (gated by `--confirm`) | 4 / 4 |
| **Overall** | | **25 / 25** |

## Improvements applied during iteration

Two changes informed by qualitative observations from the runs:

1. **SKILL.md** — added an explicit "Update merge is shallow" warning in the
   register/update/delete command list. Surfaced from eval-2: the natural
   instinct of a small patch silently drops sibling environments because the
   merge is `{**current, **patch}` at the top level. The note tells the
   agent to `show <name>` first, modify in place, and pipe the whole entry
   back.
2. **`scripts/registry.py` `cmd_list`** — replaced the `SOURCES` count with
   a sorted comma-separated list of source *types*, and added stable
   alphabetical row ordering. Surfaced from the eval-1 background-agent
   notes: a count tells the user how many sources exist but not which
   backends are wired, forcing a follow-up `show`.

## Things examined and intentionally not changed

- **No `description` column in `list`.** Adds row width and the description
  belongs in `show` — list is for "what's registered and where," show is
  for "what is this repo."
- **No deep-merge in `update`.** Array merge semantics are ambiguous
  (append vs replace vs merge-by-index); the explicit "show, modify, repipe"
  pattern is unsurprising and the SKILL.md note now calls this out.
- **No retry/fallback when Bash is denied.** Out of scope — the skill's
  invariant is "the script owns mutations." If the environment can't run
  Python, the right answer is to grant permission, not to bypass schema
  validation.

## Notes on test infrastructure

The original plan was to run each eval as a worktree-isolated subagent with
both `with_skill` and `without_skill` configurations for comparison.
Subagents hit Bash permission restrictions and stalled. The eval-1
background agent did complete and contributed the source-types-not-counts
suggestion that landed in iteration 1; the others were re-run from the
parent session. Future iterations can use these workspace artifacts as the
baseline for a clean re-run if subagent permissions are loosened.
