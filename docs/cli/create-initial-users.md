# Create Initial Users for SaaS

The `mas-devops-create-initial-users-for-saas` tool creates initial users for MAS SaaS deployments.

## Usage

```bash
mas-devops-create-initial-users-for-saas [OPTIONS]
```

## Description

This tool automates the creation of initial users in a MAS SaaS environment. It can read user information from either an AWS Secrets Manager secret or a local YAML file, and creates the users in both the MAS Core API and the Manage application.

## Options

### Required Options

- `--mas-instance-id`: MAS instance identifier
- `--mas-workspace-id`: MAS workspace identifier
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR)

### User Source Options (choose one)

- `--initial-users-secret-name`: AWS Secrets Manager secret name containing user data
- `--initial-users-yaml-file`: Path to local YAML file containing user data

### Port Configuration Options

- `--manage-api-port`: Port for Manage API (default: 8443)
- `--coreapi-port`: Port for Core API (default: 8444)
- `--admin-dashboard-port`: Port for Admin Dashboard (default: 8445)

## Examples

### Using AWS Secrets Manager

```bash
mas-devops-create-initial-users-for-saas \
    --mas-instance-id tgk01 \
    --mas-workspace-id masdev \
    --log-level INFO \
    --initial-users-secret-name "aws-dev/noble4/tgk01/initial_users" \
    --manage-api-port 8443 \
    --coreapi-port 8444 \
    --admin-dashboard-port 8445
```

### Using Local YAML File

```bash
mas-devops-create-initial-users-for-saas \
    --mas-instance-id tgk01 \
    --mas-workspace-id masdev \
    --log-level INFO \
    --initial-users-yaml-file /path/to/users.yaml \
    --manage-api-port 8443 \
    --coreapi-port 8444 \
    --admin-dashboard-port 8445
```

## User Data Format

### AWS Secrets Manager Format

The secret should contain a JSON object with email addresses as keys and comma-separated values:

```json
{
  "john.smith1@example.com": "primary,john1,smith1",
  "john.smith2@example.com": "primary,john2,smith2",
  "john.smith3@example.com": "secondary,john3,smith3"
}
```

Format: `"email": "role,firstName,lastName"`

### YAML File Format

```yaml
users:
  - email: john.smith1@example.com
    role: primary
    firstName: john1
    lastName: smith1
  - email: john.smith2@example.com
    role: primary
    firstName: john2
    lastName: smith2
  - email: john.smith3@example.com
    role: secondary
    firstName: john3
    lastName: smith3
```

## Prerequisites

### Port Forwarding Setup

Before running the tool, set up port forwarding for the required services:

```bash
# Forward MAS services
oc port-forward service/admin-dashboard 8445:443 -n mas-tgk01-core
oc port-forward service/coreapi 8444:443 -n mas-tgk01-core
oc port-forward service/tgk01-masdev 8443:443 -n mas-tgk01-manage
```

### /etc/hosts Configuration

Add the following entries to `/etc/hosts`:

```
127.0.0.1    tgk01-masdev.mas-tgk01-manage.svc.cluster.local
127.0.0.1    coreapi.mas-tgk01-core.svc.cluster.local
127.0.0.1    admin-dashboard.mas-tgk01-core.svc.cluster.local
```

### AWS Configuration (if using Secrets Manager)

Configure AWS credentials:

```bash
export SM_AWS_REGION="us-east-1"
export SM_AWS_ACCESS_KEY_ID="your-access-key"
export SM_AWS_SECRET_ACCESS_KEY="your-secret-key"

aws configure set default.region ${SM_AWS_REGION}
aws configure set aws_access_key_id ${SM_AWS_ACCESS_KEY_ID}
aws configure set aws_secret_access_key ${SM_AWS_SECRET_ACCESS_KEY}
```

## What It Does

The tool performs the following operations:

1. **Reads User Data**: Retrieves user information from AWS Secrets Manager or local file
2. **Creates Core Users**: Creates users in the MAS Core API
3. **Creates Manage Users**: Creates users in the Manage application
4. **Assigns Roles**: Assigns appropriate roles (primary/secondary) to users
5. **Validates Creation**: Verifies that users were created successfully

## Exit Codes

- `0`: All users created successfully
- `1`: Error occurred during user creation

## Troubleshooting

### Connection Issues

If you encounter connection issues:

1. Verify port forwarding is active
2. Check `/etc/hosts` entries
3. Ensure you're logged into the OpenShift cluster

### Authentication Issues

If authentication fails:

1. Verify AWS credentials (if using Secrets Manager)
2. Check that you have appropriate permissions
3. Ensure the secret/file exists and is readable

## Related

- [Users Module API](../api/users.md)
- [Quick Start Guide](../getting-started/quickstart.md)