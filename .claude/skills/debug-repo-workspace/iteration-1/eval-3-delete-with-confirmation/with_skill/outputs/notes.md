# Eval 3 — delete-with-confirmation

## Commands run

1. Pre-populate fixture: one payments-api entry.
2. `python3 .claude/skills/debug-repo/scripts/registry.py show payments-api` — read it back so the user can verify *before* deletion.
3. Simulated user confirmation: "yes."
4. `python3 .claude/skills/debug-repo/scripts/registry.py delete payments-api` (without `--confirm`) — verified the script refuses.
5. `python3 .claude/skills/debug-repo/scripts/registry.py delete payments-api --confirm` — actual delete.

## Result

- Step 4 exit code: 1 (`{"error": "confirmation_required", ...}` on stderr).
- Step 5 exit code: 0. `registry.json` repos array is now empty.

## Was the confirmation rule clear?

Yes — SKILL.md hard rule #2 spells it out: "Show the entry, then ask 'Delete
<name>? (yes/no)' — only proceed on a literal 'yes'." The script's belt-
and-braces refusal of `delete` without `--confirm` is a second line of
defense if the SKILL.md instruction were ever ignored.

Without that script-level guard, the natural agent behavior would be to go
straight to `delete payments-api --confirm` once the user said "remove it"
— the prompt sounds decisive, and skipping the show step would feel like
saving the user a round trip. The two-layer defense (SKILL.md rule +
script flag) catches this.
