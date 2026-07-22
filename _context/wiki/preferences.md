# Working Preferences & Standards

## Python Standards

- **Python version**: See `setup.py` `python_requires` for the minimum version
- **Style**: PEP 8, enforced via `autopep8` (pre-commit) and `flake8`
  - Max line length: **200** characters (`--max-line-length=200`)
  - Max complexity: 10 (`--max-complexity=10`)
  - Hard errors on: `E9, F63, F7, F82`
- **Imports**: Absolute imports from the package (`from mas.devops import ...`), not relative
- **Logging**: Use Python `logging` module; configure in the main module
- **Error handling**: CLI scripts must catch exceptions and exit with meaningful messages
- **Docstrings**: Describe parameters, return values, and exceptions

## Pre-Commit Hooks (must pass before commit)

```bash
pre-commit install          # one-time setup
pre-commit run              # run against changed files
pre-commit run -a           # run against all files
```

Hooks: **autopep8**, **flake8**, **detect-secrets**

## Secret Scanning

```bash
detect-secrets scan --update .secrets.baseline   # update baseline
detect-secrets audit .secrets.baseline           # audit
```

## Testing

```bash
make unit-test
# or
pytest test/src/mock
# specific test:
pytest -o log_cli=true --log-cli-level=DEBUG test/src/test_olm.py::test_create_subscription
```

- Test structure mirrors `src/`; test file for `src/module.py` → `test/test_module.py`

## Build & Install

```bash
make install    # creates .venv and pip installs package in editable mode; run once
make build      # builds wheel/tarball in dist/ (removes stale README.rst first)
make unit-test  # runs pytest test/src/mock (requires make install first)
make lint       # runs flake8 over src/ (hard errors: E9,F63,F7,F82; then advisory pass)
make clean      # removes .venv
make pyinstaller  # builds standalone binary via PyInstaller
# macOS prerequisite for build:
brew install pandoc
```

> **Note**: `make install` creates an editable install linked to `src/`, so there is no need to re-run it after each code change — only run it once (or when dependencies change).

## Adding a New CLI Tool

1. Create implementation module in `src/mas/devops/`
2. Create script in `bin/mas-devops-tool-name` or add entry point to `setup.py`
3. Add entry to `setup.py` `entry_points`
4. Add tests under `test/` mirroring module structure
5. Update `requirements.txt` if adding dependencies
6. Verify: `make install && mas-devops-tool-name --help`

## Tekton / Pipeline Development

See [tekton-development.md in project rules] for the full guide. Key points:
- Templates live in `tekton/src/` (Jinja2 `.yml.j2`)
- Generate tasks: `ansible-playbook tekton/generate-tekton-tasks.yml`
- Generate pipelines: `ansible-playbook tekton/generate-tekton-pipelines.yml`
- Output goes to `tekton/target/` (not committed)
- Naming: lowercase_with_underscores for params; UPPERCASE for env vars

## AI Collaboration Preferences

- **Response style**: Concise, code-first. Skip lengthy explanations — show the solution directly
- **Don't**: Add unrequested refactors, extra error handling, or unrelated cleanup
- **Don't**: Repeat plans or checklists already written to a file — reference the file path instead
- **Do**: Make the minimal change that solves the problem
- **Do**: Run relevant validation (lint, tests) before reporting completion
- **Do**: Offer to update the wiki after tasks that yield durable knowledge, then wait for approval
