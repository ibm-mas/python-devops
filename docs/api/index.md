# API Reference

Welcome to the MAS DevOps API reference documentation. This section provides detailed documentation for all modules, classes, and functions in the `mas-devops` package.

## Core Modules

These modules provide fundamental operations for working with OpenShift/Kubernetes and related technologies:

- **[OCP](ocp.md)**: OpenShift/Kubernetes cluster operations including namespace management, resource creation, and cluster interactions
- **[Tekton](tekton.md)**: Pipeline management, installation, and execution of Tekton pipelines for MAS automation
- **[OLM](olm.md)**: Operator Lifecycle Manager operations for installing and managing operators
- **[Utils](utils.md)**: Common utility functions and helper methods used throughout the library

## MAS Modules

Modules specifically designed for managing Maximo Application Suite:

- **[Suite](mas/suite.md)**: Core MAS suite management including installation, configuration, and lifecycle operations
- **[Apps](mas/apps.md)**: MAS application management for deploying and configuring MAS applications like Manage, Monitor, etc.

## Service Integration Modules

Modules for integrating with various services and dependencies:

- **[DB2](db2.md)**: Database operations including DB2 configuration validation and management
- **[SLS](sls.md)**: Suite License Service integration for license management
- **[AI Service](aiservice.md)**: AI/ML service management and configuration
- **[Slack](slack.md)**: Slack notification and alerting integration

## SaaS Modules

Modules for SaaS-specific operations:

- **[Job Cleaner](saas/job_cleaner.md)**: Utilities for cleaning up completed jobs in SaaS environments

## User Management

- **[Users](users.md)**: User creation and management for MAS deployments

## Module Overview

### Core Operations

The core modules provide the foundation for all MAS DevOps operations:

```python
from mas.devops.ocp import createNamespace, getResource
from mas.devops.tekton import installOpenShiftPipelines
from mas.devops.olm import installOperator
from mas.devops.utils import waitForResource
```

### MAS Management

Work with MAS suite and applications:

```python
from mas.devops.mas.suite import installMAS, configureMAS
from mas.devops.mas.apps import installApp, configureApp
```

### Service Integration

Integrate with external services:

```python
from mas.devops.db2 import validateDB2Config
from mas.devops.sls import configureSLS
from mas.devops.slack import sendSlackNotification
```

## Navigation

Use the navigation menu on the left to browse through the API documentation for each module. Each module page includes:

- Module overview and purpose
- Class and function documentation with parameters and return types
- Usage examples
- Related modules and cross-references

## Conventions

Throughout the API documentation:

- **Required parameters** are clearly marked
- **Optional parameters** include default values
- **Return types** are specified for all functions
- **Exceptions** that may be raised are documented
- **Examples** demonstrate common usage patterns

## Getting Help

If you need help using the API:

1. Check the [Quick Start Guide](../getting-started/quickstart.md) for common usage patterns
2. Review the specific module documentation for detailed information
3. Look at the [CLI Tools](../cli/index.md) for command-line usage examples
4. Visit the [GitHub repository](https://github.com/ibm-mas/python-devops) to report issues or ask questions