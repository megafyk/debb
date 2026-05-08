# Eval 1 — list-registered-repos

## Commands run

1. Pre-populate fixture:
   `cat > .claude/skills/debug-repo/registry.json <<'JSON' ... JSON` (two-entry seed).
2. `python3 .claude/skills/debug-repo/scripts/registry.py list`.

## Result

Exit 0. Output:

```
NAME          TAGS           ENVS        SOURCES            PATH
------------  -------------  ----------  -----------------  ----------------------------
billing-core  billing        production  quickwit           /tmp/dbg-eval-1/billing-core
payments-api  payments,card  production  metabase,quickwit  /tmp/dbg-eval-1/payments-api
```

`registry.json` is byte-identical to the fixture afterwards — list does not
mutate state.

## Improvements made during this iteration

The first cut showed `SOURCES` as a count (e.g. `2`) which forced the user
to run `show <name>` to learn what backends were wired. Changed it to a
sorted, comma-separated list of source types. Also sorted the output rows
by `name` so growing registries stay scannable. Both changes touched only
`cmd_list` in `scripts/registry.py`.

Considered but skipped:
- Adding a `description` column — would push the row width past 100 chars
  on real registries, hurting readability. `show <name>` is the right
  surface for descriptions.
- Dropping the `PATH` column — keep it; one of the most common reasons to
  list is "where on disk is this repo?"
