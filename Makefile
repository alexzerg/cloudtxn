SHELL := /bin/bash
CONFIRM ?=

.PHONY: demo-preload demo-up demo-check demo-status demo-stop demo-down unit package

demo-preload:
	@./scripts/demo-preload.sh

demo-up:
	@./scripts/sandbox-up.sh
	@./scripts/demo-status.sh

demo-check:
	@./scripts/web-integration.sh
	@cd bruno/CloudTxn && npx --yes @usebruno/cli@4.0.0 run -r --bail --output ../../.sandbox/bruno-report.json --format json
	@./scripts/browser-proof.sh

demo-status:
	@./scripts/demo-status.sh

demo-stop:
	@./scripts/sandbox-stop.sh

demo-down:
	@CONFIRM="$(CONFIRM)" ./scripts/sandbox-destroy.sh

unit:
	@.venv/bin/ruff check .
	@.venv/bin/mypy src
	@.venv/bin/pytest -q

package:
	@.venv/bin/python -m build
