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
  setup-graph           Build the single combined code-review-graph at the
                        workspace root (the common parent of all registered
                        repos, e.g. .../vds): register the root alias, install
                        (--platform claude-code), and build.
  migrate-graph --confirm   One-time migration off the old per-repo model:
                        unregister per-repo graph aliases, delete each repo's
                        .code-review-graph/ dir, then build the combined graph.

register/delete are local-only — they mutate registry.json and never touch the
code-review-graph. The combined graph is (re)built explicitly via setup-graph.

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
# code-review-graph (combined workspace graph)
# ---------------------------------------------------------------------------
# All registered repos live under one workspace root (e.g. .../vds). Instead of
# a graph per repo, the skill builds ONE combined graph at that root, registered
# in the CRG multi-repo registry under a single alias (the root directory name).
#
# register/delete are local-only — they mutate registry.json and never touch the
# graph. The combined graph is (re)built explicitly via `setup-graph`, and the
# old per-repo graphs are cleaned up once via `migrate-graph`.
#
# Every CRG call is best-effort: a failure is reported in the JSON response but
# never rolls back the local registry mutation.

CRG_BIN = "code-review-graph"
CRG_REGISTRY_PATH = Path.home() / ".code-review-graph" / "registry.json"


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

    Builds the single combined graph over the whole workspace tree. Slow
    (minutes for a large workspace); the skill's SKILL.md tells the agent to
    warn the user before triggering.
    """
    if skip:
        return {"ran": False, "skipped_reason": "--no-build"}

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


def _crg_install(*, path: str, skip: bool = False, timeout: int = 120) -> dict[str, Any]:
    """Run `code-review-graph install --repo <path> --platform claude-code -y`
    to wire the MCP config, hooks, and CLAUDE.md instruction injection at the
    workspace root.

    Side effects on the root: writes .mcp.json, may create/modify CLAUDE.md, and
    ensures .gitignore ignores .code-review-graph/. The `-y` flag auto-confirms
    injection so the subprocess does not hang waiting on a TTY.
    """
    if skip:
        return {"ran": False, "skipped_reason": "--no-install"}

    cli = shutil.which(CRG_BIN)
    if cli is None:
        return {"ran": False, "skipped_reason": "code-review-graph CLI not found on PATH"}

    cmd = [cli, "install", "--repo", path, "--platform", "claude-code", "-y"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {
            "ran": True,
            "ok": False,
            "command": " ".join(cmd),
            "error": f"install did not finish within {timeout}s",
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
# Combined-graph orchestration
# ---------------------------------------------------------------------------


def _workspace_root(data: dict[str, Any]) -> Path:
    """Common parent of every registered repo — the workspace root the combined
    graph is built at (e.g. .../vds). All repos are expected to live directly
    under one folder; if they don't, we can't pick a single root."""
    paths = [Path(r["path"]).resolve() for r in data.get("repos", []) if r.get("path")]
    if not paths:
        _die("no_repos", "Registry is empty — register a repo before building the combined graph.")
    parents = {p.parent for p in paths}
    if len(parents) != 1:
        listed = ", ".join(sorted(str(p) for p in parents))
        _die(
            "ambiguous_workspace_root",
            f"Registered repos span multiple parent directories ({listed}); the combined "
            "graph needs a single workspace root. Keep all repos under one folder.",
        )
    return parents.pop()


def _setup_combined_graph(root: Path, *, alias: str, do_install: bool, do_build: bool, build_timeout: int) -> dict[str, Any]:
    """Install the MCP wiring, build the single combined graph, then register the
    workspace root under one alias. Each step is best-effort and reported.

    Order matters: CRG's `register` rejects a path with no .git / .code-review-graph,
    and `build` is what creates .code-review-graph — so register must run last.
    """
    root_str = str(root)
    graph_install = _crg_install(path=root_str, skip=not do_install)
    graph_build = _crg_build(path=root_str, skip=not do_build, timeout=build_timeout)
    graph_register = _crg_sync("register", name=alias, path=root_str)
    return {
        "workspace_root": root_str,
        "alias": alias,
        "graph_install": graph_install,
        "graph_build": graph_build,
        "graph_register": graph_register,
    }


def _crg_unregister_under_root(root: Path) -> list[dict[str, Any]]:
    """Unregister every per-repo CRG alias whose path is nested under the
    workspace root (the leftovers from the old per-repo model). The root's own
    combined entry, and repos outside the root (e.g. this tool's own repo), are
    left untouched."""
    if not CRG_REGISTRY_PATH.exists():
        return []
    try:
        reg = json.loads(CRG_REGISTRY_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    root = root.resolve()
    results: list[dict[str, Any]] = []
    for entry in reg.get("repos", []):
        p = Path(entry.get("path", "")).resolve()
        if p != root and root in p.parents:
            alias = entry.get("alias") or str(p)
            res = _crg_sync("unregister", name=alias)
            results.append({"alias": alias, "ok": res.get("ok"), "stderr": res.get("stderr", "")})
    return results


def _remove_per_repo_graph_dirs(root: Path) -> list[dict[str, Any]]:
    """Delete each sub-repo's stale .code-review-graph/ directory. These are
    CRG-generated and gitignored; the combined graph at the root replaces them."""
    removed: list[dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        graph_dir = child / ".code-review-graph"
        if child.is_dir() and graph_dir.is_dir():
            try:
                shutil.rmtree(graph_dir)
                removed.append({"path": str(graph_dir), "ok": True})
            except OSError as e:
                removed.append({"path": str(graph_dir), "ok": False, "error": str(e)})
    return removed


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

    print(json.dumps(
        {
            "status": "registered",
            "entry": entry,
            "graph_note": (
                "Local registry only — the combined workspace graph was not rebuilt. "
                "Run `registry.py setup-graph` to include this repo in the graph."
            ),
        },
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
    print(json.dumps(
        {
            "status": "deleted",
            "removed": entry,
            "graph_note": (
                "The combined workspace graph still contains this repo's files until you "
                "re-run `registry.py setup-graph`."
            ),
        },
        indent=2,
    ))


def cmd_setup_graph(args: argparse.Namespace) -> None:
    data = _load_registry()
    root = _workspace_root(data)
    alias = args.alias or root.name
    report = _setup_combined_graph(
        root,
        alias=alias,
        do_install=not args.no_install,
        do_build=not args.no_build,
        build_timeout=args.timeout,
    )
    print(json.dumps({"status": "graph_setup", **report}, indent=2))


def cmd_migrate_graph(args: argparse.Namespace) -> None:
    if not args.confirm:
        _die(
            "confirmation_required",
            "migrate-graph unregisters every per-repo graph alias and DELETES each repo's "
            ".code-review-graph/ directory. Pass --confirm after the user agrees.",
        )
    data = _load_registry()
    root = _workspace_root(data)
    alias = args.alias or root.name

    unregistered = _crg_unregister_under_root(root)
    removed_dirs = _remove_per_repo_graph_dirs(root)
    setup = _setup_combined_graph(
        root,
        alias=alias,
        do_install=not args.no_install,
        do_build=not args.no_build,
        build_timeout=args.timeout,
    )

    print(json.dumps(
        {
            "status": "graph_migrated",
            "unregistered_aliases": unregistered,
            "removed_graph_dirs": removed_dirs,
            **setup,
        },
        indent=2,
    ))


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
    p_delete.set_defaults(func=cmd_delete)

    p_setup = sub.add_parser("setup-graph", help="Build the combined code-review-graph at the workspace root.")
    p_setup.add_argument("--alias", help="CRG alias for the workspace root (default: root directory name).")
    p_setup.add_argument("--no-install", action="store_true", help="Skip `install --platform claude-code` (MCP config, hooks, CLAUDE.md).")
    p_setup.add_argument("--no-build", action="store_true", help="Register/install only; skip the heavy full build.")
    p_setup.add_argument("--timeout", type=int, default=1800, help="Build timeout in seconds (default: 1800).")
    p_setup.set_defaults(func=cmd_setup_graph)

    p_migrate = sub.add_parser("migrate-graph", help="One-time migration from per-repo graphs to the combined graph. Requires --confirm.")
    p_migrate.add_argument("--confirm", action="store_true", help="Required: unregisters per-repo aliases and deletes per-repo .code-review-graph/ dirs.")
    p_migrate.add_argument("--alias", help="CRG alias for the workspace root (default: root directory name).")
    p_migrate.add_argument("--no-install", action="store_true", help="Skip `install --platform claude-code`.")
    p_migrate.add_argument("--no-build", action="store_true", help="Skip the heavy full build (run setup-graph later).")
    p_migrate.add_argument("--timeout", type=int, default=1800, help="Build timeout in seconds (default: 1800).")
    p_migrate.set_defaults(func=cmd_migrate_graph)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
