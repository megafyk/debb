# Eval 0 — register-payments-api

## Commands run (in order)

1. `rm -f .claude/skills/debug-repo/registry.json` — start clean.
2. `python3 .claude/skills/debug-repo/scripts/registry.py register <<'JSON' ... JSON` — full entry piped on stdin.

The setup mkdir was done up-front so `path` validation passes:
`mkdir -p /tmp/dbg-eval-0/payments-api`.

## Result

Exit code 0. The script printed back the registered entry. `registry.json`
now has version=1 and a single repo with the expected name, path, tags
(`["payments", "card"]`), and two connection blocks (`production` with
quickwit+metabase, `uat` with quickwit).

## Workflow feel

The skill's "register" path is straightforward: the user gives natural
language, we map it to the schema, pipe JSON to `registry.py register`. No
hand-edits, no second-guessing. The script's friendly error messages (path
not found, duplicate name, regex failure on the name field) make it safe to
just send the JSON and trust the script to catch problems.

## Near-misses

None on the happy path. The temptation in a constrained environment would be
to hand-edit `registry.json` if the script can't run; the SKILL.md is
explicit about not doing that, which is the right call — bypassing the
script would skip validation and silently let bad data in.
