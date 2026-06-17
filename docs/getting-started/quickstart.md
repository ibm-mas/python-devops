# Quick Start Guide

This guide will help you get started with the `mas-devops` library quickly.

## Prerequisites

Before you begin, ensure you have:

1. Python 3.12 or higher installed
2. Access to an OpenShift/Kubernetes cluster
3. Valid kubeconfig file configured
4. The `mas-devops` package installed (see [Installation](installation.md))

## Basic Usage

### 1. Import Required Modules

```python
from openshift import dynamic
from kubernetes import config
from kubernetes.client import api_client

from mas.devops.ocp import createNamespace
from mas.devops.tekton import installOpenShiftPipelines, updateTektonDefinitions
```

### 2. Create an OpenShift Client

```python
# Load kubeconfig and create a dynamic client
dynClient = dynamic.DynamicClient(
    api_client.ApiClient(configuration=config.load_kube_config())
)
```

### 3. Perform Operations

#### Create a Namespace

```python
namespace = "my-mas-namespace"
createNamespace(dynClient, namespace)
print(f"Namespace '{namespace}' created successfully")
```

#### Install OpenShift Pipelines

```python
installOpenShiftPipelines(dynClient)
print("OpenShift Pipelines installed successfully")
```

#### Update Tekton Definitions

```python
pipelinesNamespace = "mas-myinstance-pipelines"
tektonYamlPath = "/path/to/ibm-mas-tekton.yaml"

updateTektonDefinitions(dynClient, pipelinesNamespace, tektonYamlPath)
print("Tekton definitions updated successfully")
```

## Complete Example: MAS Upgrade Pipeline

Here's a complete example that sets up and launches a MAS upgrade pipeline:

```python
from openshift import dynamic
from kubernetes import config
from kubernetes.client import api_client

from mas.devops.ocp import createNamespace
from mas.devops.tekton import (
    installOpenShiftPipelines,
    updateTektonDefinitions,
    launchUpgradePipeline
)

# Configuration
instanceId = "mymas"
pipelinesNamespace = f"mas-{instanceId}-pipelines"
tektonYamlPath = "/mascli/templates/ibm-mas-tekton.yaml"

# Create OpenShift client
dynClient = dynamic.DynamicClient(
    api_client.ApiClient(configuration=config.load_kube_config())
)

# Install OpenShift Pipelines Operator
print("Installing OpenShift Pipelines...")
installOpenShiftPipelines(dynClient)

# Create pipelines namespace
print(f"Creating namespace '{pipelinesNamespace}'...")
createNamespace(dynClient, pipelinesNamespace)

# Update Tekton definitions
print("Updating Tekton definitions...")
updateTektonDefinitions(dynClient, pipelinesNamespace, tektonYamlPath)

# Launch upgrade pipeline
print("Launching upgrade pipeline...")
pipelineURL = launchUpgradePipeline(dynClient, instanceId)
print(f"Pipeline launched successfully!")
print(f"View pipeline run at: {pipelineURL}")
```

## Using CLI Tools

The package includes several command-line tools for common operations.

### Validate DB2 Configuration

```bash
mas-devops-db2-validate-config \
    --namespace mas-myinstance-core \
    --instance-name myinstance \
    --app manage
```

### Create Initial Users for SaaS

```bash
mas-devops-create-initial-users-for-saas \
    --mas-instance-id myinstance \
    --mas-workspace-id workspace1 \
    --log-level INFO \
    --initial-users-yaml-file /path/to/users.yaml \
    --manage-api-port 8443 \
    --coreapi-port 8444 \
    --admin-dashboard-port 8445
```

### Clean Up SaaS Jobs

```bash
mas-devops-saas-job-cleaner \
    --namespace mas-myinstance-core \
    --max-age-hours 24
```

### Send Slack Notification

```bash
mas-devops-notify-slack \
    --webhook-url "https://hooks.slack.com/services/YOUR/WEBHOOK/URL" \
    --message "Deployment completed successfully" \
    --channel "#deployments"
```

## Working with DB2

Validate DB2 configuration for a MAS application:

```python
from mas.devops.db2 import validateDB2Config

namespace = "mas-myinstance-core"
instanceName = "myinstance"
app = "manage"

result = validateDB2Config(namespace, instanceName, app)
if result:
    print("DB2 configuration is valid")
else:
    print("DB2 configuration validation failed")
```

## Working with Slack Notifications

Send notifications to Slack:

```python
from mas.devops.slack import sendSlackNotification

webhookUrl = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
message = "MAS deployment completed successfully"
channel = "#deployments"

sendSlackNotification(webhookUrl, message, channel)
```

## Error Handling

Always wrap your operations in try-except blocks:

```python
from mas.devops.ocp import createNamespace

try:
    createNamespace(dynClient, "my-namespace")
    print("Namespace created successfully")
except Exception as e:
    print(f"Error creating namespace: {e}")
```

## Next Steps

- Explore the [API Reference](../api/index.md) for detailed documentation
- Check out the [CLI Tools](../cli/index.md) documentation
- Learn about specific modules:
    - [OCP Operations](../api/ocp.md)
    - [Tekton Pipelines](../api/tekton.md)
    - [MAS Suite Management](../api/mas/suite.md)
    - [DB2 Operations](../api/db2.md)