# DB2 Validate Config

The `mas-devops-db2-validate-config` tool validates DB2 database configurations for MAS applications.

## Usage

```bash
mas-devops-db2-validate-config [OPTIONS]
```

## Description

This tool validates that a DB2 database instance is properly configured for use with Maximo Application Suite applications. It checks various database parameters, settings, and configurations to ensure they meet MAS requirements.

## Options

- `--namespace`: Kubernetes namespace where the DB2 instance is deployed
- `--instance-name`: Name of the MAS instance
- `--app`: MAS application name (e.g., `manage`, `iot`, `monitor`)

## Examples

### Validate DB2 for Manage Application

```bash
mas-devops-db2-validate-config \
    --namespace mas-myinstance-core \
    --instance-name myinstance \
    --app manage
```

### Validate DB2 for IoT Application

```bash
mas-devops-db2-validate-config \
    --namespace mas-prod-core \
    --instance-name prod \
    --app iot
```

## What It Checks

The tool validates:

1. **Database Configuration Parameters**: Checks critical DB2 configuration settings
2. **Database Manager Configuration**: Validates DBM configuration parameters
3. **Registry Variables**: Verifies DB2 registry settings
4. **Resource Limits**: Ensures adequate resources are allocated
5. **Connection Settings**: Validates connection parameters

## Exit Codes

- `0`: Validation successful, configuration is valid
- `1`: Validation failed, configuration issues detected

## Output

The tool provides detailed output about:

- Configuration parameters checked
- Any issues or warnings found
- Recommendations for fixing issues

## Prerequisites

- Access to the OpenShift/Kubernetes cluster
- Valid kubeconfig configured
- Appropriate permissions to access the namespace
- DB2 instance must be running

## Related

- [DB2 Module API](../api/db2.md)
- [Quick Start Guide](../getting-started/quickstart.md)