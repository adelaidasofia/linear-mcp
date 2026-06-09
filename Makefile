# Canonical CI gate. `make ci` is the ONE command both CI (ci.yml) and the local
# pre-push gate (ci-test) run, so they cannot drift. Mirrors ci.yml's test job
# exactly: pytest suite + bare smoke runner + clean-import check.
.PHONY: ci
ci:
	python -m pytest tests/ -v
	python tests/smoke.py
	LINEAR_PAT=lin_api_smoke python -c "import linear_mcp.server"
