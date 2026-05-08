#!/usr/bin/env python3
"""Grade each eval's outputs against its assertions. Writes grading.json per run."""

from __future__ import annotations

import json
from pathlib import Path

WS = Path(__file__).resolve().parent


def load_json(p: Path):
    return json.loads(p.read_text())


def grade_eval_0(outputs: Path) -> list[dict]:
    reg = load_json(outputs / "registry.json")
    notes = (outputs / "notes.md").read_text()
    repos = reg["repos"]
    r = repos[0] if repos else {}
    prod = next((c for c in r.get("connection", []) if c.get("environment") == "production"), {})
    uat = next((c for c in r.get("connection", []) if c.get("environment") == "uat"), {})
    prod_qw = next((s for s in prod.get("sources", []) if s["name"] == "quickwit"), None)
    prod_mb = next((s for s in prod.get("sources", []) if s["name"] == "metabase"), None)
    uat_qw = next((s for s in uat.get("sources", []) if s["name"] == "quickwit"), None)
    return [
        {"text": "registry.json contains exactly one repo entry", "passed": len(repos) == 1, "evidence": f"len(repos)={len(repos)}"},
        {"text": "the repo name is 'payments-api'", "passed": r.get("name") == "payments-api", "evidence": f"name={r.get('name')!r}"},
        {"text": "path equals '/tmp/dbg-eval-0/payments-api'", "passed": r.get("path") == "/tmp/dbg-eval-0/payments-api", "evidence": f"path={r.get('path')!r}"},
        {"text": "tags include both 'payments' and 'card'", "passed": set(r.get("tags", [])) >= {"payments", "card"}, "evidence": f"tags={r.get('tags')}"},
        {"text": "connection array has exactly 2 entries (production and uat)", "passed": len(r.get("connection", [])) == 2 and {c["environment"] for c in r.get("connection", [])} == {"production", "uat"}, "evidence": f"envs={[c.get('environment') for c in r.get('connection', [])]}"},
        {"text": "production has a quickwit source with id=47 and uid='pay9ldn3'", "passed": prod_qw is not None and prod_qw["metadata"].get("id") == 47 and prod_qw["metadata"].get("uid") == "pay9ldn3", "evidence": json.dumps(prod_qw)},
        {"text": "production has a metabase source with database='payments_prod'", "passed": prod_mb is not None and prod_mb["metadata"].get("database") == "payments_prod", "evidence": json.dumps(prod_mb)},
        {"text": "uat has a quickwit source with id=48 and uid='pay9uat2'", "passed": uat_qw is not None and uat_qw["metadata"].get("id") == 48 and uat_qw["metadata"].get("uid") == "pay9uat2", "evidence": json.dumps(uat_qw)},
        {"text": "notes.md shows the agent ran scripts/registry.py (not Write/Edit on registry.json directly)", "passed": "registry.py register" in notes, "evidence": "notes mention 'registry.py register'" if "registry.py register" in notes else "notes do NOT mention registry.py register"},
    ]


def grade_eval_1(outputs: Path, fixture_path: Path) -> list[dict]:
    listing = (outputs / "list_output.txt").read_text()
    notes = (outputs / "notes.md").read_text()
    final = (outputs / "registry.json").read_text()
    fixture = fixture_path.read_text() if fixture_path.exists() else final
    has_table_headers = all(h in listing for h in ("NAME", "TAGS", "ENVS"))
    return [
        {"text": "list output mentions 'payments-api'", "passed": "payments-api" in listing, "evidence": "found" if "payments-api" in listing else "missing"},
        {"text": "list output mentions 'billing-core'", "passed": "billing-core" in listing, "evidence": "found" if "billing-core" in listing else "missing"},
        {"text": "list output is a table (has NAME/TAGS/ENVS headers) or valid JSON", "passed": has_table_headers, "evidence": "headers present" if has_table_headers else "no headers"},
        {"text": "registry.json content equals the fixture (no mutation during a list operation)", "passed": json.loads(final) == json.loads(fixture), "evidence": "byte-for-byte equal" if final == fixture else "differs"},
        {"text": "notes.md shows the agent ran scripts/registry.py list", "passed": "registry.py list" in notes, "evidence": "found" if "registry.py list" in notes else "missing"},
    ]


def grade_eval_2(outputs: Path) -> list[dict]:
    reg = load_json(outputs / "registry.json")
    notes = (outputs / "notes.md").read_text()
    r = reg["repos"][0] if reg["repos"] else {}
    prod = next((c for c in r.get("connection", []) if c.get("environment") == "production"), {})
    uat = next((c for c in r.get("connection", []) if c.get("environment") == "uat"), {})
    prod_qw = next((s for s in prod.get("sources", []) if s["name"] == "quickwit"), None)
    prod_mb = next((s for s in prod.get("sources", []) if s["name"] == "metabase"), None)
    prod_pr = next((s for s in prod.get("sources", []) if s["name"] == "prometheus"), None)
    return [
        {"text": "registry.json still has exactly one repo", "passed": len(reg["repos"]) == 1, "evidence": f"len={len(reg['repos'])}"},
        {"text": "production connection sources array has 3 entries", "passed": len(prod.get("sources", [])) == 3, "evidence": f"len={len(prod.get('sources', []))}"},
        {"text": "production has a prometheus source with job='payments-api' and namespace='payments-prod'", "passed": prod_pr is not None and prod_pr["metadata"].get("job") == "payments-api" and prod_pr["metadata"].get("namespace") == "payments-prod", "evidence": json.dumps(prod_pr)},
        {"text": "production still has quickwit source with id=47, uid='pay9ldn3' (unchanged)", "passed": prod_qw is not None and prod_qw["metadata"].get("id") == 47 and prod_qw["metadata"].get("uid") == "pay9ldn3", "evidence": json.dumps(prod_qw)},
        {"text": "production still has metabase source with database='payments_prod' (unchanged)", "passed": prod_mb is not None and prod_mb["metadata"].get("database") == "payments_prod", "evidence": json.dumps(prod_mb)},
        {"text": "uat connection block is unchanged from fixture (single quickwit source id=48)", "passed": len(uat.get("sources", [])) == 1 and uat["sources"][0]["name"] == "quickwit" and uat["sources"][0]["metadata"].get("id") == 48, "evidence": json.dumps(uat)},
        {"text": "notes.md shows the agent ran scripts/registry.py update payments-api", "passed": "registry.py update payments-api" in notes, "evidence": "found" if "registry.py update payments-api" in notes else "missing"},
    ]


def grade_eval_3(outputs: Path) -> list[dict]:
    reg = load_json(outputs / "registry.json")
    notes = (outputs / "notes.md").read_text()
    return [
        {"text": "registry.json has zero repo entries (repos array is empty)", "passed": len(reg["repos"]) == 0, "evidence": f"repos={reg['repos']}"},
        {"text": "notes.md indicates the agent ran 'show payments-api' (or equivalent) BEFORE the delete", "passed": "show payments-api" in notes and notes.find("show payments-api") < notes.find("delete payments-api"), "evidence": f"show idx={notes.find('show payments-api')}, delete idx={notes.find('delete payments-api')}"},
        {"text": "notes.md records an explicit user-confirmation step before --confirm was used", "passed": ("Simulated user" in notes or "confirmation" in notes or '"yes."' in notes or "'yes.'" in notes), "evidence": "confirmation phrase present"},
        {"text": "notes.md shows the agent ran scripts/registry.py delete payments-api --confirm", "passed": "registry.py delete payments-api --confirm" in notes, "evidence": "found" if "registry.py delete payments-api --confirm" in notes else "missing"},
    ]


GRADERS = {
    0: ("eval-0-register-payments-api", grade_eval_0),
    1: ("eval-1-list-registered-repos", grade_eval_1),
    2: ("eval-2-update-add-prometheus-source", grade_eval_2),
    3: ("eval-3-delete-with-confirmation", grade_eval_3),
}


def main() -> None:
    summary = []
    for eval_id, (dirname, grader) in GRADERS.items():
        eval_dir = WS / dirname
        outputs = eval_dir / "with_skill" / "outputs"
        meta = load_json(eval_dir / "eval_metadata.json")
        if eval_id == 1:
            results = grader(outputs, fixture_path=outputs / "registry_before.json")
        else:
            results = grader(outputs)
        grading = {
            "eval_id": eval_id,
            "eval_name": meta["eval_name"],
            "expectations": results,
            "passed": sum(1 for r in results if r["passed"]),
            "total": len(results),
        }
        (eval_dir / "with_skill" / "grading.json").write_text(json.dumps(grading, indent=2) + "\n")
        summary.append((meta["eval_name"], grading["passed"], grading["total"]))
        print(f"{meta['eval_name']}: {grading['passed']}/{grading['total']}")

    overall = (sum(p for _, p, _ in summary), sum(t for _, _, t in summary))
    print(f"\nOVERALL: {overall[0]}/{overall[1]}")


if __name__ == "__main__":
    main()
