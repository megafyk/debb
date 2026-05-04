.PHONY: graph-install graph-build graph-status graph-serve

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
