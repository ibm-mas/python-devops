# CLI Tools

The `mas-devops` package includes several command-line tools for common MAS DevOps operations.

## Available Tools

### [DB2 Validate Config](db2-validate-config.md)
Validate DB2 database configurations for MAS applications.

```bash
mas-devops-db2-validate-config --help
```

### [Create Initial Users](create-initial-users.md)
Create initial users for MAS SaaS deployments.

```bash
mas-devops-create-initial-users-for-saas --help
```

### [SaaS Job Cleaner](saas-job-cleaner.md)
Clean up completed jobs in SaaS environments.

```bash
mas-devops-saas-job-cleaner --help
```

### [Notify Slack](notify-slack.md)
Send notifications to Slack channels.

```bash
mas-devops-notify-slack --help
```

## Common Usage Patterns

### Port Forwarding for Local Development

When working with MAS locally, you often need to set up port forwarding:

```bash
# Forward MAS core services
oc port-forward service/admin-dashboard 8445:443 -n mas-instance-core
oc port-forward service/coreapi 8444:443 -n mas-instance-core
oc port-forward service/instance-app 8443:443 -n mas-instance-app
```

### Environment Setup

Set up your environment variables:

```bash
# AWS credentials for secrets management
export SM_AWS_REGION="us-east-1"
export SM_AWS_ACCESS_KEY_ID="your-access-key"
export SM_AWS_SECRET_ACCESS_KEY="your-secret-key"

# Configure AWS CLI
aws configure set default.region ${SM_AWS_REGION}
aws configure set aws_access_key_id ${SM_AWS_ACCESS_KEY_ID}
aws configure set aws_secret_access_key ${SM_AWS_SECRET_ACCESS_KEY}
```

### OpenShift Login

Log in to your OpenShift cluster:

```bash
oc login --token=sha256~your-token --server=https://api.cluster.example.com:6443
```

## Tool Installation

All CLI tools are automatically installed when you install the `mas-devops` package:

```bash
pip install mas-devops
```

After installation, the tools will be available in your PATH.

## Getting Help

Each tool provides detailed help information:

```bash
# Get help for any tool
mas-devops-db2-validate-config --help
mas-devops-create-initial-users-for-saas --help
mas-devops-saas-job-cleaner --help
mas-devops-notify-slack --help
```

## Next Steps

- Learn about each tool in detail by clicking on the links above
- Check the [API Reference](../api/index.md) for programmatic usage
- Review the [Quick Start Guide](../getting-started/quickstart.md) for examples