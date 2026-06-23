# python-devops AI Coding Instructions

## Project Overview
Python package for IBM Maximo DevOps utilities. Provides command-line tools for deployment automation, database validation, Slack notifications, and user management. Distributed as installable package with `setup.py`/`pyproject.toml` and standalone scripts in `bin/`.

## Architecture
- **bin/**: Executable CLI scripts (entry points)
  - `mas-devops-*`: Command-line tools for specific operations
  - Scripts import from `src/` package for implementation
  - Each script typically wraps a single operational task
- **src/**: Main package source code
  - Organized by module/function (import path: `from mas_devops import ...`)
  - Core utilities: configuration management, API clients, database handlers
- **test/**: Test suite (pytest structure)
  - Mirror `src/` structure in test files
  - Run with `pytest` or `make test`
- **build/**: Generated artifacts (don't edit)
  - `*.egg-info/`: Package metadata
  - `dist/`, `*.whl`: Distribution packages
- **setup.py** / **pyproject.toml**: Package definition
  - Entry points defined in setup.py pointing to `bin/` scripts
  - Dependencies in both files (must keep in sync)
  - Version defined once (check both files)

## Key Patterns
- **CLI Tool Pattern**: `bin/mas-devops-*` scripts are thin wrappers
  - Import main logic from `src/mas_devops/`
  - Handle argument parsing and error reporting
  - Example: `mas-devops-notify-slack` → calls slack notification module
- **Dependency Management**:
  - Core dependencies in `setup.py` `install_requires`
  - Dev dependencies in `setup.py` `extras_require['dev']`
  - `requirements.txt` for pinned versions (reproducible installs)
  - Keep all three in sync
- **Entry Points**: `setup.py` defines CLI commands
  - Format: `'mas-devops-task-name = mas_devops.module:main_function'`
  - Creates executable scripts in `bin/` when package installed
- **Module Organization**: Import directly from package
  - `from mas_devops.db2_validator import validate_config`
  - Avoid deep nesting; keep public API clear

## Development Workflow
```bash
make install           # Install package in dev mode (pip install -e .)
make test              # Run pytest suite
make test-verbose      # Pytest with verbose output
make build             # Build distribution (wheel/tarball)
make clean             # Remove build artifacts
make all               # Clean, test, build
```

## Important Conventions
- **Python Version**: Check `setup.py` for `python_requires` (e.g., `>=3.8`)
- **Entry Points**: Adding new CLI tool requires editing `setup.py` entry_points section
- **Error Handling**: CLI scripts should catch exceptions and exit with meaningful error messages
- **Logging**: Use Python logging module; configure in main module
- **Testing**: Test structure mirrors source; test file for `src/module.py` is `test/test_module.py`
- **Documentation**: Docstrings in functions should describe parameters, return, exceptions
- **Imports**: Use absolute imports from package (`from mas_devops import ...`), not relative

## Common CLI Tools (Reference)
- `mas-devops-create-initial-users-for-saas`: User provisioning (SaaS)
- `mas-devops-db2-validate-config`: Validate DB2 configuration
- `mas-devops-notify-slack`: Send notifications
- `mas-devops-saas-job-cleaner`: Cleanup SaaS jobs

## Integration Points
- **ansible-devops**: Playbooks call these Python utilities for infrastructure setup
- **playbook**: Runbooks document procedures; Python tools automate them
- **Standalone Usage**: Scripts can be called independently or from other tools via entry points
- **Distribution**: Package installed via pip; entry points register CLI commands globally

## When Adding New CLI Tool
1. Create implementation module in `src/mas_devops/`
2. Create script in `bin/mas-devops-tool-name` or update `setup.py` entry_points
3. Add entry to `setup.py` entry_points section
4. Add tests in `test/` matching module structure
5. Update `requirements.txt` if adding dependencies
6. Test with `make install` then run `mas-devops-tool-name --help`

## Packaging & Distribution
- Build: `python -m build` or `make build`
- Outputs: wheel file in `dist/` ready for pip install
- Version managed in `setup.py` (check both setup.py and pyproject.toml)
