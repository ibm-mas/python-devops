# MAS DevOps

Welcome to the **MAS DevOps** documentation! This Python library provides tools and utilities for managing Maximo Application Suite (MAS) deployments and operations.

[![Code style: PEP8](https://img.shields.io/badge/code%20style-PEP--8-blue.svg)](https://peps.python.org/pep-0008/)
[![Flake8: checked](https://img.shields.io/badge/flake8-checked-blueviolet)](https://flake8.pycqa.org/en/latest/)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ibm-mas/python-devops/python-release.yml)
[![PyPI - Version](https://img.shields.io/pypi/v/mas.devops)](https://pypi.org/project/mas-devops)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/mas.devops)
![PyPI - Downloads](https://img.shields.io/pypi/dm/mas.devops)

## Overview

The `mas-devops` package provides a comprehensive set of Python modules and CLI tools for:

- **OpenShift/Kubernetes Operations**: Manage namespaces, resources, and deployments
- **Tekton Pipelines**: Install and manage OpenShift Pipelines for MAS automation
- **Operator Lifecycle Manager (OLM)**: Handle operator installations and subscriptions
- **MAS Suite Management**: Configure and manage MAS instances and applications
- **Database Operations**: Validate and configure DB2 instances
- **SaaS Operations**: Clean up jobs and manage SaaS-specific tasks
- **User Management**: Create and manage initial users for MAS
- **Notifications**: Send alerts and notifications via Slack

## Quick Example

```python
from openshift import dynamic
from kubernetes import config
from kubernetes.client import api_client

from mas.devops.ocp import createNamespace
from mas.devops.tekton import installOpenShiftPipelines, updateTektonDefinitions, launchUpgradePipeline

instanceId = "mymas"
pipelinesNamespace = f"mas-{instanceId}-pipelines"

# Create an OpenShift client
dynClient = dynamic.DynamicClient(
    api_client.ApiClient(configuration=config.load_kube_config())
)

# Install OpenShift Pipelines Operator
installOpenShiftPipelines(dynamicClient)

# Create the pipelines namespace and install the MAS tekton definitions
createNamespace(dynamicClient, pipelinesNamespace)
updateTektonDefinitions(dynamicClient, pipelinesNamespace, "/mascli/templates/ibm-mas-tekton.yaml")

# Launch the upgrade pipeline and print the URL to view the pipeline run
pipelineURL = launchUpgradePipeline(self.dynamicClient, instanceId)
print(pipelineURL)
```

## Features

### Core Modules

- **OCP**: OpenShift/Kubernetes cluster operations
- **Tekton**: Pipeline management and execution
- **OLM**: Operator lifecycle management
- **Utils**: Common utilities and helper functions

### MAS Modules

- **Suite**: MAS core suite management
- **Apps**: MAS application configuration and deployment

### Service Integrations

- **DB2**: Database validation and configuration
- **SLS**: Suite License Service integration
- **AI Service**: AI/ML service management
- **Slack**: Notification and alerting

### CLI Tools

The package includes several command-line tools:

- `mas-devops-db2-validate-config`: Validate DB2 configurations
- `mas-devops-create-initial-users-for-saas`: Create initial users for SaaS deployments
- `mas-devops-saas-job-cleaner`: Clean up completed jobs in SaaS environments
- `mas-devops-notify-slack`: Send notifications to Slack channels

## Getting Started

Check out the [Installation Guide](getting-started/installation.md) to get started, or jump straight to the [Quick Start](getting-started/quickstart.md) guide.

## API Reference

Browse the complete [API Reference](api/index.md) for detailed documentation of all modules, classes, and functions.

## Contributing

We welcome contributions! Please see our [Contributing Guide](contributing.md) for details on how to get involved.

## License

This project is licensed under the Eclipse Public License v1.0. See the [License](license.md) page for details.