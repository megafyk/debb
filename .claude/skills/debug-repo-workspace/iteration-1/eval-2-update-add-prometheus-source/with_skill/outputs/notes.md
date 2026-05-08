# Eval 2 — update-add-prometheus-source

## Commands run

1. Pre-populate fixture: payments-api with production (quickwit+metabase) and uat (quickwit).
2. `python3 .claude/skills/debug-repo/scripts/registry.py update payments-api <<'JSON' ... JSON`
   — patch contained the **full** `connection` array (both production with three sources and uat unchanged).

## Result

Exit 0. Final state: production has 3 sources (quickwit, metabase,
prometheus), uat unchanged. The script printed a `changed.connection`
diff with `before`/`after` blocks.

## The shallow-merge gotcha

The natural first instinct was to send a "small" patch like:

```json
{ "connection": [ { "environment": "production", "sources": [ { "name": "prometheus", ... } ] } ] }
```

That would have **silently dropped uat and clobbered the existing prod
sources**, because the merge is top-level shallow (`{**current, **patch}`)
— a `connection` key in the patch wholly replaces the `connection` key in
the current entry.

Fix applied to SKILL.md: an explicit "Update merge is shallow" warning that
tells the agent to `show <name>` first, modify the JSON in place, then
pipe the whole thing back to `update`. This makes the failure mode
unsurprising.

Alternative considered: implement deep merge in the script. Rejected —
ambiguous semantics for arrays (append? replace? merge by index?) and the
"show then re-pipe" pattern is explicit about what changed.
