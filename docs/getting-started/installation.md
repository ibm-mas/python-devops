# Installation

## Requirements

- Python 3.12 or higher
- pip package manager

## Install from PyPI

The easiest way to install `mas-devops` is from PyPI:

```bash
pip install mas-devops
```

## Install from Source

To install the latest development version from source:

```bash
git clone https://github.com/ibm-mas/python-devops.git
cd python-devops
pip install -e .
```

## Install with Development Dependencies

If you want to contribute to the project, install with development dependencies:

```bash
pip install -e ".[dev]"
```

This will install additional tools for testing and development:

- `build`: Build tool for creating distributions
- `flake8`: Code linting
- `pytest`: Testing framework
- `pytest-mock`: Mocking support for tests
- `requests-mock`: HTTP request mocking

## Install with Documentation Dependencies

To build the documentation locally:

```bash
pip install -e ".[docs]"
```

This installs:

- `mkdocs`: Documentation site generator
- `mkdocs-material`: Material theme for MkDocs
- `mkdocstrings[python]`: Automatic documentation from docstrings
- `pymdown-extensions`: Markdown extensions

## Verify Installation

After installation, verify that the package is installed correctly:

```python
import mas.devops
print(mas.devops.__version__)
```

You should also be able to run the CLI tools:

```bash
mas-devops-db2-validate-config --help
mas-devops-create-initial-users-for-saas --help
mas-devops-saas-job-cleaner --help
mas-devops-notify-slack --help
```

## Dependencies

The package requires the following runtime dependencies:

- `pyyaml`: YAML parsing and generation
- `openshift`: OpenShift/Kubernetes client
- `kubernetes`: Kubernetes Python client
- `kubeconfig`: Kubeconfig file handling
- `jinja2`: Template engine
- `jinja2-base64-filters`: Base64 filters for Jinja2
- `semver`: Semantic versioning
- `boto3`: AWS SDK for Python
- `slack_sdk`: Slack API client

All dependencies will be automatically installed when you install the package.

## Next Steps

Once installed, proceed to the [Quick Start Guide](quickstart.md) to learn how to use the library.