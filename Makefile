.PHONY: graph-install graph-build graph-status graph-serve test test-boundary lint

graph-install:
	uv sync
	uv run code-review-graph install --platform claude-code --yes

graph-build:
	uv run code-review-graph build

graph-status:
	uv run code-review-graph status

graph-serve:
	uv run code-review-graph serve

test:
	uv run --package evidence-gate pytest evidence_gate/tests/ -v

test-boundary:
	uv run --package evidence-gate pytest evidence_gate/tests/boundary/ -v

lint:
	uv run --package evidence-gate python -m py_compile evidence_gate/evidence_gate/mcp_server/tools.py
	uv run --package evidence-gate python -c "import evidence_gate.mcp_server.tools; print('imports OK')"
