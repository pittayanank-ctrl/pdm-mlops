# Contributing

- `main` is protected: every change goes through a branch + Pull Request, needs 1 review and green CI.
- Branch names: `feat/<area>-<thing>`, `fix/...`, `test/...`, `ci/...`, `docs/...`, `chore/...`.
- Commit messages: `type(scope): what changed` e.g. `feat(serving): add /predict/batch endpoint`.
- Before pushing: `pytest`, `ruff check src tests`, `ruff format src tests`.
- Do not commit generated files (`data/`, `reports/`, `mlruns/`, `mlflow.db`) - they are rebuilt by the pipeline.
- Configuration lives in `configs/params.yaml`; never hard-code thresholds or dates in code.
- If you used an AI assistant for a change, say which part in the PR description (required by the course).
