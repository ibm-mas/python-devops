# Notify Slack

The `mas-devops-notify-slack` tool sends notifications to Slack channels for cluster provisioning events.

## Usage

```bash
mas-devops-notify-slack --action ACTION --rc RETURN_CODE [--msg MESSAGE]
```

## Description

This tool sends notifications to Slack channels about OpenShift cluster provisioning status. It supports notifications for both Fyre and ROKS (IBM Cloud) cluster deployments. The tool uses the Slack API via a bot token to post formatted messages.

## Environment Variables

### Required

- `SLACK_TOKEN`: Slack bot token for authentication
- `SLACK_CHANNEL`: Comma-separated list of Slack channels to notify (e.g., `#deployments,#alerts`)
- `CLUSTER_NAME`: Name of the cluster being provisioned

### Action-Specific Variables

#### For Successful Fyre Provisioning (`--action ocp-provision-fyre` with `--rc 0`)

- `OCP_CONSOLE_URL`: OpenShift console URL
- `OCP_USERNAME`: OpenShift admin username
- `OCP_PASSWORD`: OpenShift admin password

#### For Successful ROKS Provisioning (`--action ocp-provision-roks` with `--rc 0`)

- `OCP_CONSOLE_URL`: OpenShift console URL

#### Optional (for both actions)

- `TOOLCHAIN_PIPELINERUN_URL`: URL to the pipeline run
- `TOOLCHAIN_TRIGGER_NAME`: Name of the pipeline trigger

## Options

### Required Options

- `--action`: Action type (choices: `ocp-provision-fyre`, `ocp-provision-roks`)
- `--rc`: Return code (0 for success, non-zero for failure)

### Optional Options

- `--msg`: Additional message to include in the notification

## Examples

### Notify Fyre Cluster Provisioning Success

```bash
export SLACK_TOKEN="xoxb-your-slack-token"
export SLACK_CHANNEL="#deployments"
export CLUSTER_NAME="dev-cluster-01"
export OCP_CONSOLE_URL="https://console-openshift-console.apps.dev-cluster-01.example.com"
export OCP_USERNAME="kubeadmin"
export OCP_PASSWORD="xxxxx-xxxxx-xxxxx-xxxxx"

mas-devops-notify-slack \
    --action ocp-provision-fyre \
    --rc 0 \
    --msg "Additional deployment notes"
```

### Notify Fyre Cluster Provisioning Failure

```bash
export SLACK_TOKEN="xoxb-your-slack-token"
export SLACK_CHANNEL="#alerts"
export CLUSTER_NAME="dev-cluster-01"

mas-devops-notify-slack \
    --action ocp-provision-fyre \
    --rc 1
```

### Notify ROKS Cluster Provisioning Success

```bash
export SLACK_TOKEN="xoxb-your-slack-token"
export SLACK_CHANNEL="#deployments,#cloud-ops"
export CLUSTER_NAME="prod-roks-cluster"
export OCP_CONSOLE_URL="https://console-openshift-console.apps.prod-roks-cluster.us-south.containers.appdomain.cloud"

mas-devops-notify-slack \
    --action ocp-provision-roks \
    --rc 0
```

### Notify ROKS Cluster Provisioning Failure

```bash
export SLACK_TOKEN="xoxb-your-slack-token"
export SLACK_CHANNEL="#alerts"
export CLUSTER_NAME="prod-roks-cluster"

mas-devops-notify-slack \
    --action ocp-provision-roks \
    --rc 1
```

## Slack Bot Setup

### Creating a Slack Bot

1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name your app (e.g., "MAS DevOps Bot") and select your workspace
4. Navigate to "OAuth & Permissions"
5. Add the following Bot Token Scopes:
   - `chat:write` - Send messages
   - `chat:write.public` - Send messages to channels without joining
6. Install the app to your workspace
7. Copy the "Bot User OAuth Token" (starts with `xoxb-`)

### Storing Slack Token Securely

Store the token as an environment variable or secret:

```bash
# Environment variable
export SLACK_TOKEN="xoxb-your-slack-token"

# Or use a secret management system
export SLACK_TOKEN=$(aws secretsmanager get-secret-value --secret-id slack-token --query SecretString --output text)
```

## Message Format

The tool sends formatted Slack messages with:

- **Success messages** include:
  - Cluster name
  - Console URL
  - Credentials (for Fyre)
  - Links to management dashboards
  - Optional additional message

- **Failure messages** include:
  - Cluster name
  - Links to management dashboards
  - Pipeline run link (if available)

## Integration Examples

### GitHub Actions

```yaml
- name: Notify Slack on Fyre Provisioning
  if: always()
  env:
    SLACK_TOKEN: ${{ secrets.SLACK_TOKEN }}
    SLACK_CHANNEL: "#deployments"
    CLUSTER_NAME: ${{ steps.provision.outputs.cluster_name }}
    OCP_CONSOLE_URL: ${{ steps.provision.outputs.console_url }}
    OCP_USERNAME: ${{ steps.provision.outputs.username }}
    OCP_PASSWORD: ${{ steps.provision.outputs.password }}
  run: |
    mas-devops-notify-slack \
      --action ocp-provision-fyre \
      --rc ${{ steps.provision.outcome == 'success' && '0' || '1' }}
```

### Tekton Pipeline

```yaml
- name: notify-slack
  image: your-registry/mas-devops:latest
  env:
    - name: SLACK_TOKEN
      valueFrom:
        secretKeyRef:
          name: slack-credentials
          key: token
    - name: SLACK_CHANNEL
      value: "#deployments"
    - name: CLUSTER_NAME
      value: "$(params.cluster-name)"
    - name: OCP_CONSOLE_URL
      value: "$(tasks.provision.results.console-url)"
  script: |
    mas-devops-notify-slack \
      --action ocp-provision-roks \
      --rc 0 \
      --msg "Provisioned via Tekton pipeline"
```

### Shell Script

```bash
#!/bin/bash
# provision-and-notify.sh

export SLACK_TOKEN="xoxb-your-slack-token"
export SLACK_CHANNEL="#deployments"
export CLUSTER_NAME="dev-cluster-01"

# Provision cluster
if provision_fyre_cluster.sh; then
    # Set success environment variables
    export OCP_CONSOLE_URL="https://console.example.com"
    export OCP_USERNAME="kubeadmin"
    export OCP_PASSWORD="xxxxx-xxxxx"

    # Notify success
    mas-devops-notify-slack \
        --action ocp-provision-fyre \
        --rc 0 \
        --msg "Cluster provisioned successfully"
else
    # Notify failure
    mas-devops-notify-slack \
        --action ocp-provision-fyre \
        --rc 1
    exit 1
fi
```

## Best Practices

1. **Secure Token Storage**: Always store `SLACK_TOKEN` as a secret, never in code
2. **Multiple Channels**: Use comma-separated channels for different audiences
3. **Include Context**: Use `--msg` to add deployment-specific information
4. **Error Handling**: Always check return codes and notify on failures
5. **Environment Cleanup**: Clear sensitive environment variables after use

## Troubleshooting

### No Notification Sent

If no notification is sent, the tool exits silently when:

1. `SLACK_TOKEN` environment variable is not set
2. `SLACK_CHANNEL` environment variable is not set

This is by design to allow the tool to be used in environments where Slack notifications are optional.

### Missing Required Environment Variables

If you get an error about missing environment variables:

1. Verify `CLUSTER_NAME` is set
2. For success notifications (`--rc 0`):
   - Fyre: Check `OCP_CONSOLE_URL`, `OCP_USERNAME`, `OCP_PASSWORD`
   - ROKS: Check `OCP_CONSOLE_URL`

### Authentication Errors

If you get Slack API authentication errors:

1. Verify your `SLACK_TOKEN` is valid and starts with `xoxb-`
2. Check that the bot has the required permissions
3. Ensure the bot is installed in your workspace

### Channel Not Found

If messages aren't appearing in the expected channel:

1. Verify channel names include the `#` prefix
2. Check that the bot has access to the channel
3. For private channels, invite the bot to the channel first

## Exit Codes

- `0`: Notification sent successfully
- `1`: Error sending notification

## Related

- [Slack Module API](../api/slack.md)
- [Quick Start Guide](../getting-started/quickstart.md)

## What It Does

The tool performs the following operations:

1. **Checks Environment**: Verifies required environment variables are set
2. **Parses Channels**: Splits comma-separated channel list
3. **Builds Message**: Creates formatted Slack message blocks based on action and return code
4. **Posts to Slack**: Sends message to all specified channels using Slack API
5. **Returns Status**: Exits with appropriate code based on success/failure

## Supported Actions

### `ocp-provision-fyre`

Sends notifications about Fyre (IBM DevIT) OpenShift cluster provisioning:

- **Success** (`--rc 0`): Includes console URL, credentials, and Fyre dashboard link
- **Failure** (`--rc 1`): Includes Fyre dashboard link for troubleshooting

### `ocp-provision-roks`

Sends notifications about ROKS (IBM Cloud) OpenShift cluster provisioning:

- **Success** (`--rc 0`): Includes console URL and IBM Cloud dashboard link
- **Failure** (`--rc 1`): Includes IBM Cloud dashboard link for troubleshooting

## Exit Codes

- `0`: Notification sent successfully (or silently skipped if SLACK_TOKEN/SLACK_CHANNEL not set)
- `1`: Error occurred (missing required environment variables for the action)