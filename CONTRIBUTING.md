Developer Guide
===============================================================================

Tests
-------------------------------------------------------------------------------
```
pytest -o log_cli=true --log-cli-level=DEBUG test/src/test_olm.py::test_create_subscription
```


Detect Secrets
-------------------------------------------------------------------------------
- Update the `.secrets.baseline` file using: `detect-secrets scan --update .secrets.baseline`
- Audit secrets using: `detect-secrets audit .secrets.baseline`


Pre-Commit Hooks
-------------------------------------------------------------------------------
The follow pre-commit hooks are enabled:

- **autopep8**
- **flake8**
- **detect-secrets**

These hooks are also executed in a GitHub action in the [pre-commit workflow](.github/workflows/pre-commit.yml).

```bash
python -m pip install pre-commit --upgrade
pre-commit install
```

Manually run the pre-commit hooks against changed files
```bash
pre-commit run
```

Manually run the pre-commit hooks against all files
```bash
pre-commit run -a
```

Building locally
-------------------------------------------------------------------------------
Clone the python-devops repository locally. From the top level directory, run
```
make install build
```

NOTE: if building on MacOS you will need to first install pandoc:
```
brew install pandoc
```