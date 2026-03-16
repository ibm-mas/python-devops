# Contributing to MAS DevOps

Thank you for your interest in contributing to the MAS DevOps project! This guide will help you get started.

## Getting Started

### Prerequisites

- Python 3.12 or higher
- Git
- Access to an OpenShift/Kubernetes cluster (for testing)
- Familiarity with Python development

### Setting Up Development Environment

1. **Fork and Clone the Repository**

```bash
git clone https://github.com/YOUR_USERNAME/python-devops.git
cd python-devops
```

2. **Create a Virtual Environment**

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install Development Dependencies**

```bash
pip install -e ".[dev]"
```

4. **Install Pre-commit Hooks**

```bash
pre-commit install
```

## Development Workflow

### 1. Create a Branch

Create a new branch for your feature or bug fix:

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### 2. Make Changes

- Write clean, readable code following PEP 8 style guidelines
- Add docstrings to all functions, classes, and modules
- Include type hints where appropriate
- Write tests for new functionality

### 3. Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=mas.devops

# Run specific test file
pytest test/src/test_ocp.py
```

### 4. Check Code Quality

```bash
# Run flake8 linter
flake8 src/

# Run pre-commit checks
pre-commit run --all-files
```

### 5. Commit Changes

Write clear, descriptive commit messages:

```bash
git add .
git commit -m "Add feature: description of your changes"
```

### 6. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub.

## Code Style Guidelines

### Python Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) style guide
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 120 characters
- Use meaningful variable and function names

### Docstring Format

Use Google-style docstrings:

```python
def example_function(param1: str, param2: int) -> bool:
    """Brief description of the function.

    Longer description if needed, explaining what the function does,
    any important details, or usage notes.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: Description of when this error is raised

    Examples:
        >>> result = example_function("test", 42)
        >>> print(result)
        True
    """
    # Implementation
    return True
```

### Type Hints

Use type hints for function parameters and return values:

```python
from typing import List, Dict, Optional

def process_data(items: List[str], config: Dict[str, any]) -> Optional[str]:
    """Process data with configuration."""
    # Implementation
    pass
```

## Testing Guidelines

### Writing Tests

- Place tests in the `test/` directory
- Mirror the source structure in test directory
- Use descriptive test names: `test_function_name_expected_behavior`
- Use pytest fixtures for common setup
- Mock external dependencies

Example test:

```python
import pytest
from mas.devops.ocp import createNamespace

def test_create_namespace_success(mock_client):
    """Test successful namespace creation."""
    namespace = "test-namespace"
    result = createNamespace(mock_client, namespace)
    assert result is True
```

### Running Specific Tests

```bash
# Run tests for a specific module
pytest test/src/test_ocp.py

# Run a specific test function
pytest test/src/test_ocp.py::test_create_namespace_success

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=mas.devops --cov-report=html
```

## Documentation

### Updating Documentation

When adding new features or making changes:

1. Update relevant docstrings
2. Add or update documentation in `docs/`
3. Update README.md if needed
4. Add examples to demonstrate usage

### Building Documentation Locally

```bash
# Install documentation dependencies
pip install -e ".[docs]"

# Build documentation
mkdocs build

# Serve documentation locally
mkdocs serve
```

Then visit http://localhost:8000 to view the documentation.

## Pull Request Process

1. **Ensure All Tests Pass**: Run the full test suite
2. **Update Documentation**: Add or update relevant documentation
3. **Follow Code Style**: Ensure code passes flake8 checks
4. **Write Clear Description**: Explain what your PR does and why
5. **Link Related Issues**: Reference any related issues
6. **Request Review**: Tag appropriate reviewers

### PR Checklist

- [ ] Tests added/updated and passing
- [ ] Documentation updated
- [ ] Code follows style guidelines
- [ ] Commit messages are clear
- [ ] No merge conflicts
- [ ] Pre-commit hooks pass

## Reporting Issues

### Bug Reports

When reporting bugs, include:

- Clear description of the issue
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment details (Python version, OS, etc.)
- Error messages or logs

### Feature Requests

When requesting features, include:

- Clear description of the feature
- Use case and motivation
- Proposed implementation (if any)
- Examples of how it would be used

## Code Review Process

All contributions go through code review:

1. Automated checks run on PR creation
2. Maintainers review code and provide feedback
3. Address feedback and update PR
4. Once approved, PR is merged

## Community Guidelines

- Be respectful and inclusive
- Provide constructive feedback
- Help others learn and grow
- Follow the project's code of conduct

## Getting Help

If you need help:

- Check existing documentation
- Search existing issues
- Ask questions in pull requests
- Contact maintainers

## License

By contributing, you agree that your contributions will be licensed under the Eclipse Public License v1.0.

## Additional Resources

- [Project README](../README.md)
- [API Documentation](api/index.md)
- [Quick Start Guide](getting-started/quickstart.md)
- [GitHub Repository](https://github.com/ibm-mas/python-devops)

Thank you for contributing to MAS DevOps! 🎉