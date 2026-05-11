#!/usr/bin/env python3
"""Service repo registry CRUD for the debug-repo skill.

The registry lives next to this script at ../registry.json. All mutations are
atomic (temp file + os.replace) and gated by JSON Schema validation.

Commands:
  register              Read a full entry as JSON on stdin and append it.
  list [--json]         List entries as a table (default) or JSON.
  show <name> [--json]  Print one entry.
  update <name>         Read a partial-or-full entry as JSON on stdin and merge it.
  delete <name> --confirm   Remove an entry. --confirm is required.

Errors are printed as JSON on stderr and the script exits non-zero. The skill
relays those errors verbatim to the user.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:
    print(
        json.dumps(
            {
                "error": "missing_dependency",
                "message": "Python package 'jsonschema' is required. Install with: pip install jsonschema",
            }
        ),
        file=sys.stderr,
    )
    sys.exit(2)


SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_DIR = SKILL_DIR / "schemas"
REGISTRY_PATH = SKILL_DIR / "registry.json"


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------


def _load_schema(filename: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / filename).read_text())


def _entry_schema_with_inline_refs() -> dict[str, Any]:
    """Return the entry schema with source $refs inlined.

    jsonschema's $ref resolution across files needs a registry; inlining is
    simpler and keeps the script self-contained.
    """
    entry = _load_schema("registry_entry.schema.json")
    sources = {
        "quickwit": _load_schema("source_quickwit.schema.json"),
        "metabase": _load_schema("source_metabase.schema.json"),
        "prometheus": _load_schema("source_prometheus.schema.json"),
    }
    one_of = entry["definitions"]["source"]["oneOf"]
    for branch in one_of:
        const = branch["properties"]["name"]["const"]
        branch["properties"]["metadata"] = sources[const]
    return entry


ENTRY_SCHEMA = _entry_schema_with_inline_refs()


# ---------------------------------------------------------------------------
# Registry IO
# ---------------------------------------------------------------------------


def _load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"version": 1, "repos": []}
    data = json.loads(REGISTRY_PATH.read_text())
    if "version" not in data or "repos" not in data:
        _die("invalid_registry", f"Registry at {REGISTRY_PATH} is malformed.")
    return data


def _save_registry(data: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".registry-", suffix=".json", dir=str(REGISTRY_PATH.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.write("\n")
        os.replace(tmp_path, REGISTRY_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def _find_entry(repos: list[dict[str, Any]], name: str) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    for i, r in enumerate(repos):
        if r.get("name") == name:
            return i, r
    return None, None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_entry(entry: dict[str, Any]) -> None:
    try:
        jsonschema.validate(entry, ENTRY_SCHEMA)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) or "(root)"
        _die("schema_validation_failed", f"At {path}: {e.message}")

    # Path existence check (jsonschema can't do this).
    path = entry.get("path", "")
    if not os.path.isdir(path):
        _die(
            "path_not_found",
            f"path '{path}' does not exist or is not a directory. Provide an absolute path to an existing repo.",
        )


def _die(code: str, message: str) -> None:
    print(json.dumps({"error": code, "message": message}), file=sys.stderr)
    sys.exit(1)


def _read_json_stdin() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        _die("empty_stdin", "Expected a JSON object on stdin.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        _die("invalid_json", f"stdin is not valid JSON: {e}")


# ---------------------------------------------------------------------------
# code-review-graph sync
# ---------------------------------------------------------------------------
# The debug-repo registry mirrors a subset of itself into the code-review-graph
# multi-repo registry at ~/.code-review-graph/registry.json. CRG only stores
# {path, alias} per repo; we map debug-repo's `name` → CRG's `alias`.
#
# Sync is best-effort: a failure here logs a warning into the JSON response
# but does NOT roll back the local mutation. The two registries can drift
# (e.g. user added a repo to CRG manually) and that's recoverable; rolling
# back the local op on a CRG hiccup would surprise the user more than it
# helps.

CRG_BIN = "code-review-graph"


def _crg_sync(action: str, *, name: str, path: str | None = None, skip: bool = False) -> dict[str, Any]:
    """Run `code-review-graph register/unregister` and return a structured report.

    `action` is "register" or "unregister".
    For register, both `name` (alias) and `path` are required.
    For unregister, only `name` (passed as path_or_alias) is needed.
    """
    if skip:
        return {"ran": False, "skipped_reason": "--no-graph-sync"}

    cli = shutil.which(CRG_BIN)
    if cli is None:
        return {
            "ran": False,
            "skipped_reason": "code-review-graph CLI not found on PATH",
            "hint": "install with `pip install code-review-graph` or pass --no-graph-sync",
        }

    if action == "register":
        cmd = [cli, "register", path, "--alias", name]
    elif action == "unregister":
        cmd = [cli, "unregister", name]
    else:
        return {"ran": False, "skipped_reason": f"unknown action {action!r}"}

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ran": True, "ok": False, "command": " ".join(cmd), "error": str(e)}

    return {
        "ran": True,
        "ok": proc.returncode == 0,
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _crg_build(*, path: str, skip: bool = False, timeout: int = 600) -> dict[str, Any]:
    """Run `code-review-graph build --repo <path>` to parse the repo into the graph.

    Called after a successful register so a freshly registered repo has a graph
    ready to query. Slow (seconds to minutes depending on repo size); the
    skill's SKILL.md tells the agent to warn the user before triggering.
    """
    if skip:
        return {"ran": False, "skipped_reason": "--no-graph-build"}

    cli = shutil.which(CRG_BIN)
    if cli is None:
        return {"ran": False, "skipped_reason": "code-review-graph CLI not found on PATH"}

    cmd = [cli, "build", "--repo", path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {
            "ran": True,
            "ok": False,
            "command": " ".join(cmd),
            "error": f"build did not finish within {timeout}s — graph may be partially built",
        }
    except OSError as e:
        return {"ran": True, "ok": False, "command": " ".join(cmd), "error": str(e)}

    return {
        "ran": True,
        "ok": proc.returncode == 0,
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_register(args: argparse.Namespace) -> None:
    entry = _read_json_stdin()
    _validate_entry(entry)
    data = _load_registry()
    idx, _ = _find_entry(data["repos"], entry["name"])
    if idx is not None:
        _die("duplicate_name", f"A repo named '{entry['name']}' already exists. Use 'update' to modify it.")
    data["repos"].append(entry)
    _save_registry(data)

    graph_sync = _crg_sync("register", name=entry["name"], path=entry["path"], skip=args.no_graph_sync)

    # Only build if the register actually landed in CRG — otherwise the build
    # will also fail and we'd just be returning the same error twice.
    if args.no_graph_sync or not graph_sync.get("ok"):
        graph_build = {"ran": False, "skipped_reason": "graph_sync did not succeed; nothing to build"}
    else:
        graph_build = _crg_build(path=entry["path"], skip=args.no_graph_build)

    print(json.dumps(
        {"status": "registered", "entry": entry, "graph_sync": graph_sync, "graph_build": graph_build},
        indent=2,
    ))


def cmd_list(args: argparse.Namespace) -> None:
    data = _load_registry()
    repos = data["repos"]
    if args.json:
        print(json.dumps(repos, indent=2))
        return

    if not repos:
        print("(registry is empty — use `register` to add a repo)")
        return

    rows = []
    for r in sorted(repos, key=lambda x: x["name"]):
        envs = ",".join(c["environment"] for c in r.get("connection", []))
        source_names = sorted({s["name"] for c in r.get("connection", []) for s in c.get("sources", [])})
        sources = ",".join(source_names) if source_names else "-"
        tags = ",".join(r.get("tags", []))
        rows.append((r["name"], tags, envs, sources, r.get("path", "")))

    headers = ("NAME", "TAGS", "ENVS", "SOURCES", "PATH")
    widths = [max(len(h), max((len(row[i]) for row in rows), default=0)) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        print(fmt.format(*row))


def cmd_show(args: argparse.Namespace) -> None:
    data = _load_registry()
    _, entry = _find_entry(data["repos"], args.name)
    if entry is None:
        _die("not_found", f"No repo named '{args.name}'.")
    print(json.dumps(entry, indent=2))


def cmd_update(args: argparse.Namespace) -> None:
    patch = _read_json_stdin()
    data = _load_registry()
    idx, current = _find_entry(data["repos"], args.name)
    if idx is None:
        _die("not_found", f"No repo named '{args.name}'. Use 'register' to add it.")

    # Disallow renaming via update — that's error-prone. User must delete + register.
    if "name" in patch and patch["name"] != args.name:
        _die(
            "rename_not_supported",
            f"Update cannot change 'name' (got '{patch['name']}', expected '{args.name}'). "
            "Use delete + register for renames.",
        )

    merged = {**current, **patch, "name": args.name}
    _validate_entry(merged)
    data["repos"][idx] = merged
    _save_registry(data)

    diff = {k: {"before": current.get(k), "after": merged.get(k)} for k in patch if current.get(k) != merged.get(k)}
    print(json.dumps({"status": "updated", "name": args.name, "changed": diff}, indent=2))


def cmd_delete(args: argparse.Namespace) -> None:
    if not args.confirm:
        _die("confirmation_required", "Pass --confirm to actually delete. Skill must show the entry and ask the user first.")
    data = _load_registry()
    idx, entry = _find_entry(data["repos"], args.name)
    if idx is None:
        _die("not_found", f"No repo named '{args.name}'.")
    data["repos"].pop(idx)
    _save_registry(data)
    graph_sync = _crg_sync("unregister", name=args.name, skip=args.no_graph_sync)
    print(json.dumps({"status": "deleted", "removed": entry, "graph_sync": graph_sync}, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="registry.py",
        description="Service repo registry for the debug-repo skill.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_register = sub.add_parser("register", help="Append a new entry. Reads JSON from stdin.")
    p_register.add_argument("--no-graph-sync", action="store_true", help="Skip the code-review-graph register call (also skips build).")
    p_register.add_argument("--no-graph-build", action="store_true", help="Run register in CRG but skip the slower full graph build.")
    p_register.set_defaults(func=cmd_register)

    p_list = sub.add_parser("list", help="List all entries.")
    p_list.add_argument("--json", action="store_true", help="Output JSON instead of a table.")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Print one entry as JSON.")
    p_show.add_argument("name")
    p_show.add_argument("--json", action="store_true", help="(default; kept for symmetry with list)")
    p_show.set_defaults(func=cmd_show)

    p_update = sub.add_parser("update", help="Merge a JSON patch into an entry. Reads JSON from stdin.")
    p_update.add_argument("name")
    p_update.set_defaults(func=cmd_update)

    p_delete = sub.add_parser("delete", help="Remove an entry. Requires --confirm.")
    p_delete.add_argument("name")
    p_delete.add_argument("--confirm", action="store_true", help="Required to actually delete.")
    p_delete.add_argument("--no-graph-sync", action="store_true", help="Skip the code-review-graph unregister call.")
    p_delete.set_defaults(func=cmd_delete)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
