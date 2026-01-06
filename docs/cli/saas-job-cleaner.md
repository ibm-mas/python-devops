# SaaS Job Cleaner

The `mas-devops-saas-job-cleaner` tool cleans up completed jobs in SaaS environments.

## Usage

```bash
mas-devops-saas-job-cleaner [OPTIONS]
```

## Description

This tool automatically cleans up completed Kubernetes jobs in MAS SaaS environments. It helps maintain a clean cluster by removing old job resources that are no longer needed, preventing resource accumulation and improving cluster performance.

## Options

- `--namespace`: Kubernetes namespace to clean jobs from
- `--max-age-hours`: Maximum age in hours for completed jobs (default: 24)
- `--dry-run`: Preview what would be deleted without actually deleting
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR)

## Examples

### Clean Jobs Older Than 24 Hours

```bash
mas-devops-saas-job-cleaner \
    --namespace mas-myinstance-core \
    --max-age-hours 24
```

### Clean Jobs Older Than 48 Hours

```bash
mas-devops-saas-job-cleaner \
    --namespace mas-prod-core \
    --max-age-hours 48 \
    --log-level INFO
```

### Dry Run (Preview Only)

```bash
mas-devops-saas-job-cleaner \
    --namespace mas-myinstance-core \
    --max-age-hours 24 \
    --dry-run \
    --log-level DEBUG
```

### Clean Multiple Namespaces

```bash
# Clean jobs in multiple namespaces
for ns in mas-inst1-core mas-inst2-core mas-inst3-core; do
    mas-devops-saas-job-cleaner \
        --namespace $ns \
        --max-age-hours 24 \
        --log-level INFO
done
```

## What It Does

The tool performs the following operations:

1. **Scans Namespace**: Lists all jobs in the specified namespace
2. **Filters Completed Jobs**: Identifies jobs that have completed (succeeded or failed)
3. **Checks Age**: Determines which jobs are older than the specified age
4. **Deletes Jobs**: Removes jobs that meet the criteria
5. **Reports Results**: Provides summary of deleted jobs

## Job Selection Criteria

Jobs are selected for deletion if they meet ALL of the following criteria:

- Job status is "Completed" (either succeeded or failed)
- Job completion time is older than `--max-age-hours`
- Job is in the specified namespace

## Prerequisites

- Access to the OpenShift/Kubernetes cluster
- Valid kubeconfig configured
- Appropriate permissions to list and delete jobs in the namespace
- Must be logged into the cluster

## Safety Features

### Dry Run Mode

Use `--dry-run` to preview what would be deleted:

```bash
mas-devops-saas-job-cleaner \
    --namespace mas-myinstance-core \
    --max-age-hours 24 \
    --dry-run
```

This will show you which jobs would be deleted without actually deleting them.

### Age Protection

The tool only deletes jobs older than the specified age, protecting recent jobs from accidental deletion.

## Automation

### Cron Job Setup

You can automate job cleanup using a Kubernetes CronJob:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: job-cleaner
  namespace: mas-myinstance-core
spec:
  schedule: "0 2 * * *"  # Run daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: job-cleaner
            image: your-registry/mas-devops:latest
            command:
            - mas-devops-saas-job-cleaner
            - --namespace
            - mas-myinstance-core
            - --max-age-hours
            - "24"
            - --log-level
            - INFO
          restartPolicy: OnFailure
```

### Script Automation

Create a script to clean multiple namespaces:

```bash
#!/bin/bash
# cleanup-jobs.sh

NAMESPACES=(
    "mas-inst1-core"
    "mas-inst2-core"
    "mas-inst3-core"
)

MAX_AGE=24
LOG_LEVEL="INFO"

for ns in "${NAMESPACES[@]}"; do
    echo "Cleaning jobs in namespace: $ns"
    mas-devops-saas-job-cleaner \
        --namespace "$ns" \
        --max-age-hours "$MAX_AGE" \
        --log-level "$LOG_LEVEL"
done
```

## Output

The tool provides detailed output including:

- Number of jobs scanned
- Number of jobs eligible for deletion
- List of deleted jobs
- Any errors encountered

Example output:

```
INFO: Scanning namespace mas-myinstance-core for completed jobs
INFO: Found 15 completed jobs
INFO: 8 jobs are older than 24 hours
INFO: Deleting job: data-import-job-20231201
INFO: Deleting job: backup-job-20231202
...
INFO: Successfully deleted 8 jobs
```

## Exit Codes

- `0`: Cleanup completed successfully
- `1`: Error occurred during cleanup

## Best Practices

1. **Start with Dry Run**: Always test with `--dry-run` first
2. **Conservative Age**: Start with a longer age (e.g., 48 hours) and adjust as needed
3. **Regular Schedule**: Run regularly (e.g., daily) to prevent accumulation
4. **Monitor Logs**: Review logs to ensure expected behavior
5. **Namespace Specific**: Run separately for each namespace to maintain control

## Troubleshooting

### Permission Denied

If you get permission errors:

```bash
# Verify you have the correct permissions
oc auth can-i delete jobs -n mas-myinstance-core
```

### No Jobs Deleted

If no jobs are deleted:

1. Check that jobs exist: `oc get jobs -n mas-myinstance-core`
2. Verify job completion status
3. Check job age against `--max-age-hours`
4. Use `--dry-run` to see what would be deleted

## Related

- [SaaS Job Cleaner Module API](../api/saas/job_cleaner.md)
- [Quick Start Guide](../getting-started/quickstart.md)