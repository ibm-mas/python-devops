# mas-devops-feature-status-update

Writes MAS feature status records to the DevOps MongoDB (`mas_devops` database).
Routes writes to `instance_level_config` (instance-scoped) or `cluster_level_config`
(cluster-scoped) depending on whether `--instance-id` is supplied.

## Database behaviour

| Scenario | `mas_devops` database | Collections | Other collections | Data |
|---|---|---|---|---|
| `mas_devops` missing | ✅ Created automatically on first write | ✅ Created with validator + indexes | Not touched | N/A — fresh start |
| `mas_devops` exists | Not modified | Not modified | Not touched | N/A |
| Collections missing | N/A | ✅ Created with validator + indexes | Not touched | N/A — fresh start |
| Collections exist | Not modified | Not modified (validator + indexes unchanged) | Not touched | Existing docs updated in-place; `created_at` preserved; unrelated feature entries in array unchanged |

## Prerequisites

- Python 3
- `pymongo` — `pip install pymongo`
- MongoDB 6+ (for local development — see [Local MongoDB](#local-mongodb))

## Local MongoDB

Two options to run a local MongoDB instance for development and testing.

### Option A — Docker (recommended)

```bash
# Start a MongoDB 7 container, data persisted in a named volume
docker run -d \
  --name mongodb-local \
  -p 27017:27017 \
  -v mongodb-local-data:/data/db \
  mongo:7

# Verify it is running
docker ps --filter name=mongodb-local

# Stop / restart
docker stop mongodb-local
docker start mongodb-local

# Remove container and volume (destroys all data)
docker rm -f mongodb-local
docker volume rm mongodb-local-data
```

Connection URL: `mongodb://localhost:27017`

### Option B — Homebrew (macOS)

```bash
# Install
brew tap mongodb/brew
brew install mongodb-community

# Start as a background service (auto-restarts on login)
brew services start mongodb-community

# Or run in the foreground (current terminal only)
mongod --config /opt/homebrew/etc/mongod.conf

# Stop
brew services stop mongodb-community
```

Connection URL: `mongodb://localhost:27017`

---

### Initialize the `mas_devops` database

No separate step is required. Once MongoDB is running and `DEVOPS_MONGO_URI`
is exported, the first `status-update` call automatically creates both
collections (with JSON Schema validators) and all required indexes.

Verify the collections were created after the first write:

```bash
mongosh "mongodb://localhost:27017/feature_dashboard" --eval "db.getCollectionNames()"
# Expected: [ 'cluster_level_config', 'instance_level_config' ]
```

### Set the connection URI

Set `DEVOPS_MONGO_URI` — all commands read it automatically. Credentials and TLS options are embedded directly in the URI, matching the convention used across all other DevOps pipeline scripts:

```bash
export DEVOPS_MONGO_URI='mongodb://user:password@host1:port1,host2:port2/admin?tls=true&tlsAllowInvalidCertificates=true'  # pragma: allowlist secret
```

No separate verification step is needed — the first `status-update` call will
create required indexes automatically if they are absent.

---

## Installation

### From the package (recommended)

Install the `mas-devops` package and the script is placed on `$PATH` automatically:

```bash
# Install from PyPI
pip install mas-devops

# Or install from source (editable)
git clone https://github.com/ibm-mas/python-devops.git
cd python-devops
pip install -e .
```

Once installed, run the script directly:

```bash
mas-devops-feature-status-update <command> [options]
```

### Run directly from source (without installing)

```bash
# From the repository root
python bin/mas-devops-feature-status-update <command> [options]

# Or make the script executable and run it
chmod +x bin/mas-devops-feature-status-update
./bin/mas-devops-feature-status-update <command> [options]
```

### Built-in help

```bash
# Top-level help
mas-devops-feature-status-update --help

# Sub-command help
mas-devops-feature-status-update status-update --help
mas-devops-feature-status-update get --help
```

---

## Sub-commands

### `status-update`

Upserts a feature status document.
Upsert key: `(region, instance_id, account, cluster, type)` — an existing document is updated in-place; a new document is inserted if no match is found.

Required collection indexes (`instance_config_level`, `cluster_config_level`) are created automatically on the first call if they are absent — no separate setup step is needed.

**Idempotency:** Safe to call multiple times with the same arguments. The underlying `find_one_and_update` with `upsert=True` guarantees that re-running with the same identity key produces the same final document state. `created_at` is set only on the first insert (`$setOnInsert`); subsequent calls update `updated_at` and all mutable fields without creating duplicate documents.

**Identity options**

| Flag | Required | Description |
|------|----------|-------------|
| `--region` | Yes | AWS region (e.g. `us-east-2`) |
| `--instance-id` | Instance-level types | MAS instance ID (e.g. `inst02`). When supplied routes to `instance_level_config`; when omitted routes to `cluster_level_config`. |
| `--account` | Yes | GitOps account name (e.g. `fyre-noble10-dev`) |
| `--cluster` | Yes | GitOps cluster name (e.g. `noble10`) |
| `--subscription-id` | Instance-level types | Subscription ID. Required when `--instance-id` is supplied; must be omitted for cluster-level feature types. |

**Feature options** *(all required)*

| Flag | Description |
|------|-------------|
| `--type` | Feature type (e.g. `allow-list`) |
| `--feature-details JSON` | Type-specific JSON payload. `allow-list` requires an `ips` array. |

**Status options** *(all required)*

| Flag | Description |
|------|-------------|
| `--status` | One of `REQUESTED`, `IN_PROGRESS`, `ACTIVE`, `ERROR` |
| `--status-details JSON` | JSON object describing the outcome (see schema below). Mutually exclusive with `--status-details-file`. |
| `--status-details-file FILE` | Path to a JSON file containing the status-details object. Use this for `ERROR` payloads whose `message` or `stacktrace` contains quote characters that would break inline shell interpolation. Mutually exclusive with `--status-details`. |

**Timestamp options** *(all optional, default: current UTC time)*

| Flag | Description |
|------|-------------|
| `--deployment-start ISO-8601` | Start of the deployment |
| `--deployment-end ISO-8601` | End of the deployment |
| `--created-at ISO-8601` | Overrides `created_at` on document insert only |
| `--updated-at ISO-8601` | Overrides `updated_at` |

The MongoDB connection URI is read from the `DEVOPS_MONGO_URI` environment variable — no connection flags are needed on the command line.

**`--status-details` schema**

`request_configuration` is a free-form string describing what was requested — it may be a single CIDR, a comma-separated list, or a space-separated list. The validator does not enforce format.

*REQUESTED* — pipeline has received the request but processing has not yet started.
```json
{
  "message": "Allow list request received.",
  "request_configuration": "2405:201:d000:9062::/64"
}
```

*IN_PROGRESS* — pipeline is actively deploying the feature.
```json
{
  "message": "Allow list deployment in progress.",
  "request_configuration": "2405:201:d000:9062::/64"
}
```

*ACTIVE* — deployment completed successfully. Multiple IPs may be comma-separated.
```json
{
  "message": "Allow list is active.",
  "request_configuration": "1.2.3.4/32, 2405:201:d000:9062::/64"
}
```

*ERROR* — deployment failed. `error_source` fields are all optional except that the object itself is required. Use `--status-details-file` when `message` or `stacktrace` may contain quote characters.
```json
{
  "message": "sample error message",
  "error_code": 401,
  "error_source": {
    "gitops_version": "8.6.0",
    "filename": "cis_ip_allowlist.yml",
    "log_file": "/var/log/gitops/run-001.log",
    "stacktrace": "Traceback (most recent call last): ..."
  },
  "request_configuration": "2405:201:d000:9060::/64"
}
```

**Examples**

```bash
# REQUESTED status — record that a request has been received
mas-devops-feature-status-update status-update \
    --region us-east-2 \
    --instance-id inst02 \
    --account fyre-noble10-dev \
    --cluster noble10 \
    --subscription-id sub-id01 \
    --type allow-list \
    --feature-details '{"ips": ["2405:201:d000:9062::/64"]}' \
    --status REQUESTED \
    --status-details '{"message": "Allow list request received.", "request_configuration": "2405:201:d000:9062::/64"}' \
    --deployment-start 2026-09-11T11:48:42+00:00

# IN_PROGRESS status — record that deployment has started
mas-devops-feature-status-update status-update \
    --region us-east-2 \
    --instance-id inst02 \
    --account fyre-noble10-dev \
    --cluster noble10 \
    --subscription-id sub-id01 \
    --type allow-list \
    --feature-details '{"ips": ["2405:201:d000:9062::/64"]}' \
    --status IN_PROGRESS \
    --status-details '{"message": "Allow list deployment in progress.", "request_configuration": "2405:201:d000:9062::/64"}' \
    --deployment-start 2026-09-11T11:48:42+00:00

# ACTIVE status — single IP
mas-devops-feature-status-update status-update \
    --region us-east-2 \
    --instance-id inst02 \
    --account fyre-noble10-dev \
    --cluster noble10 \
    --subscription-id sub-id01 \
    --type allow-list \
    --feature-details '{"ips": ["2405:201:d000:9062::/64"]}' \
    --status ACTIVE \
    --status-details '{"message": "Allow list is active.", "request_configuration": "2405:201:d000:9062::/64"}' \
    --deployment-start 2026-09-11T11:48:42+00:00 \
    --deployment-end   2026-09-11T11:53:10+00:00

# ACTIVE status — multiple IPs (request_configuration is comma-separated)
mas-devops-feature-status-update status-update \
    --region us-east-2 \
    --instance-id inst02 \
    --account fyre-noble10-dev \
    --cluster noble10 \
    --subscription-id sub-id01 \
    --type allow-list \
    --feature-details '{"ips": ["1.2.3.4/32", "2405:201:d000:9062::/64"]}' \
    --status ACTIVE \
    --status-details '{"message": "Allow list is active.", "request_configuration": "1.2.3.4/32, 2405:201:d000:9062::/64"}' \
    --deployment-start 2026-09-11T11:48:42+00:00 \
    --deployment-end   2026-09-11T11:53:10+00:00

# ERROR status — use --status-details-file to avoid shell quoting issues with error text
cat > /tmp/status-details.json <<'EOF'
{
  "message": "sample error message",
  "error_code": 401,
  "error_source": {
    "gitops_version": "8.6.0",
    "filename": "cis_ip_allowlist.yml",
    "log_file": "/var/log/gitops/run-001.log",
    "stacktrace": "Traceback (most recent call last): ..."
  },
  "request_configuration": "2405:201:d000:9060::/64"
}
EOF
mas-devops-feature-status-update status-update \
    --region us-east-2 \
    --instance-id inst02 \
    --account fyre-noble10-dev \
    --cluster noble10 \
    --subscription-id sub-id01 \
    --type allow-list \
    --feature-details '{"ips": ["2405:201:d000:9060::/64"]}' \
    --status ERROR \
    --status-details-file /tmp/status-details.json \
    --deployment-start 2026-09-11T11:48:42+00:00 \
    --deployment-end   2026-09-11T11:53:10+00:00
```

---

### `get`

Fetches a single feature status document and prints it as formatted JSON.

Two mutually exclusive lookup modes are supported — exactly one must be provided:

- **`--id`** — look up by ObjectId (the value printed by `status-update` on success).
- **`--region` + criteria flags** — look up by the document's identifying fields.

**Idempotency:** Read-only. Safe to call any number of times with no side effects.

**Arguments**

| Argument | Required | Description |
|----------|----------|-------------|
| `--id OBJECT_ID` | One of `--id` / `--region` | 24-character hex ObjectId |
| `--region REGION` | One of `--id` / `--region` | AWS region (e.g. `us-east-2`). Enables criteria-based lookup |
| `--instance-id INSTANCE_ID` | Yes (criteria mode) | MAS instance ID (e.g. `inst02`) |
| `--account ACCOUNT` | Yes (criteria mode) | GitOps account name (e.g. `fyre-noble10-dev`) |
| `--cluster CLUSTER` | Yes (criteria mode) | GitOps cluster name (e.g. `noble10`) |
| `--subscription-id SUBSCRIPTION_ID` | Yes (criteria mode) | Subscription ID |
| `--type TYPE` | Yes (criteria mode) | Feature type (e.g. `allow-list`) |

The MongoDB connection URI is read from `DEVOPS_MONGO_URI` — no connection flags are needed.

**Example — by ObjectId**

```bash
mas-devops-feature-status-update get \
    --id 6ab0e70ee6d3a31faa808547
```

**Example — by criteria**

```bash
mas-devops-feature-status-update get \
    --region us-east-2 \
    --instance-id inst02 \
    --account fyre-noble10-dev \
    --cluster noble10 \
    --subscription-id sub-id01 \
    --type allow-list
```

**Sample output**

```json
{
  "_id": "<doc-id>",
  "schema_version": 1,
  "region": "us-east-2",
  "instance_id": "inst02",
  "account": "fyre-noble10-dev",
  "cluster": "noble10",
  "subscription_id": "sub-id01",
  "type": "allow-list",
  "feature_details": { "ips": ["2405:201:d000:9062::/64"] },
  "status": "ACTIVE",
  "status_details": { "message": "Allow list is active.", "request_configuration": "2405:201:d000:9062::/64" },
  "deployment_start": "2026-09-11 11:48:42+00:00",
  "deployment_end": "2026-09-11 11:53:10+00:00",
  "created_at": "2026-09-11 11:48:42+00:00",
  "updated_at": "2026-09-11 11:48:42+00:00"
}
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DEVOPS_MONGO_URI` | Yes | Full MongoDB connection URI with embedded credentials and TLS options. |

```bash
export DEVOPS_MONGO_URI='mongodb://user:password@host1:port1,host2:port2/admin?tls=true&tlsAllowInvalidCertificates=true'  # pragma: allowlist secret
```

---

## Database Setup

The `feature_dashboard` MongoDB database must be initialised before this tool can write records. It holds two collections:

| Collection | Cardinality |
|---|---|
| `cluster_level_config` | One document per `account × region × cluster` |
| `instance_level_config` | One document per `subscription_id × account × region × cluster × instance` |

### Initialize

No separate step is required. The first `status-update` call automatically
creates both collections with strict JSON Schema validators and all required
indexes. The operation is idempotent — subsequent calls are no-ops.

### Clear data (keep schema & indexes)

```js
use feature_dashboard
db.cluster_level_config.deleteMany({})
db.instance_level_config.deleteMany({})
```

### Drop collections (removes schema & indexes)

```js
use feature_dashboard
db.cluster_level_config.drop()
db.instance_level_config.drop()
```

### Drop collections (removes schema & indexes) with auth
```
mongosh "mongodb://mas_devops_user:mas_devops_password@localhost:27017/mas_devops?authSource=mas_devops&tls=false&tlsAllowInvalidCertificates=true" \  # pragma: allowlist secret
  --eval "
db.cluster_level_config.drop()
db.instance_level_config.drop()
print('collections dropped')
"
```

> **Note:** `drop()` removes the collection, all documents, and all indexes. They are recreated automatically on the next `status-update` call.

### Indexes created automatically on first write

**`cluster_level_config`**

| Index name | Fields | Unique |
|---|---|---|
| `ux_cluster_level_config_account_region_cluster` | `account, region, cluster` | ✓ |
| `ix_cluster_level_config_account` | `account` | |

**`instance_level_config`**

| Index name | Fields | Unique |
|---|---|---|
| `ux_instance_level_config_sub_account_region_cluster_instance` | `subscription_id, account, region, cluster, instance` | ✓ |
| `ix_instance_level_config_sub_account_region_cluster` | `subscription_id, account, region, cluster` | |
| `ix_instance_level_config_feature_status` | `instance_level_features.status` | |
| `ix_instance_level_config_error_code` | `instance_level_features.status_details.error_code` (sparse) | |

### Validation behaviour

Both collections enforce:

```js
validationLevel: "strict"   // enforced on inserts AND updates
validationAction: "error"   // rejects non-conforming writes outright
```

`additionalProperties: false` is set on every top-level and nested object (except `cluster_level_features[]` items, which allow extension fields).

---

## MongoDB Document Schema

### `mas_devops.instance_level_config`

One document per `(subscription_id × account × region × cluster × instance)`.
Feature entries are embedded in the `instance_level_features[]` array.

```json
{
  "_id": "<ObjectId>",
  "subscription_id": "sub-id01",
  "account": "fyre-noble10-dev",
  "region": "us-east-2",
  "cluster": "noble10",
  "instance": "inst02",
  "instance_level_features": [
    {
      "type": "allow-list",
      "feature_details": { "ips": ["2405:201:d000:9062::/64"] },
      "status": "ACTIVE",
      "status_details": { "message": "Allow list is active.", "request_configuration": "2405:201:d000:9062::/64" },
      "deployment_start": "<ISO-8601>",
      "deployment_end": "<ISO-8601>",
      "source": "ansible_devops",
      "created_at": "<ISODate>",
      "updated_at": "<ISODate>"
    }
  ],
  "created_at": "<ISODate>",
  "updated_at": "<ISODate>"
}
```

### `mas_devops.cluster_level_config`

One document per `(account × region × cluster)`.
Feature entries are embedded in the `cluster_level_features[]` array.

```json
{
  "_id": "<ObjectId>",
  "account": "fyre-noble10-dev",
  "region": "us-east-2",
  "cluster": "noble10",
  "cluster_level_features": [
    {
      "type": "<feature-type>",
      "feature_details": {},
      "status": "ACTIVE",
      "status_details": {},
      "deployment_start": "<ISO-8601>",
      "deployment_end": "<ISO-8601>",
      "source": "ansible_devops",
      "created_at": "<ISODate>",
      "updated_at": "<ISODate>"
    }
  ],
  "created_at": "<ISODate>",
  "updated_at": "<ISODate>"
}
```

---

## Global Options

| Flag | Default | Description |
|------|---------|-------------|
| `--log-level` | `WARNING` | Python logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

---

## Ansible Integration

See the full sample playbook at [`playbooks/feature-status-update.yml`](../playbooks/feature-status-update.yml).

### Minimal task — `status-update`

```yaml
- name: Upsert feature status (ACTIVE)
  ansible.builtin.command:
    cmd: >-
      mas-devops-feature-status-update status-update
      --region {{ mas_region }}
      --instance-id {{ mas_instance_id }}
      --account {{ mas_account }}
      --cluster {{ mas_cluster }}
      --subscription-id {{ mas_subscription_id }}
      --type allow-list
      --feature-details {{ '{"ips": ["2405:201:d000:9062::/64"]}' | quote }}
      --status ACTIVE
      --status-details {{ '{"message": "Allow list is active.", "request_configuration": "2405:201:d000:9062::/64"}' | quote }}
  register: status_update_result
  changed_when: "'written successfully' in status_update_result.stdout"
```

For `ERROR` status, write the payload to a file first to avoid shell quoting problems with error text:

```yaml
- name: Write ERROR status-details to file
  ansible.builtin.copy:
    dest: /tmp/mas-status-details.json
    content: |
      {
        "message": "{{ _error_msg | replace('\\', '\\\\') | replace('"', '\\"') }}",
        "error_code": {{ _error_code }},
        "error_source": {
          "gitops_version": "{{ lookup('env', 'GITOPS_VERSION') | default('', true) }}",
          "filename": "{{ _error_filename }}",
          "log_file": "{{ lookup('env', 'JUNIT_OUTPUT_DIR') | default('/var/log/gitops', true) }}/run.log",
          "stacktrace": "{{ _error_msg | replace('\\', '\\\\') | replace('"', '\\"') }}"
        },
        "request_configuration": "{{ _request_configuration }}"
      }

- name: Upsert feature status (ERROR)
  ansible.builtin.command:
    cmd: >-
      mas-devops-feature-status-update status-update
      --region {{ mas_region }}
      --instance-id {{ mas_instance_id }}
      --account {{ mas_account }}
      --cluster {{ mas_cluster }}
      --subscription-id {{ mas_subscription_id }}
      --type allow-list
      --feature-details {{ ('{"ips": ' + _normalised_ips | to_json + '}') | quote }}
      --status ERROR
      --status-details-file /tmp/mas-status-details.json
      --deployment-start {{ _deployment_start }}
      --deployment-end {{ _deployment_end }}
  register: status_update_result
  changed_when: "'written successfully' in status_update_result.stdout"
```

### Minimal task — `get`

**By ObjectId** — extract the document ID from `status-update` output and fetch the written document:

```yaml
- name: Extract document ID
  ansible.builtin.set_fact:
    mas_document_id: >-
      {{ status_update_result.stdout
         | regex_search('Document ID: ([a-f0-9]{24})', '\1')
         | first }}

- name: Fetch feature status document by ID
  ansible.builtin.command:
    cmd: >-
      mas-devops-feature-status-update get
      --id {{ mas_document_id }}
  register: get_result
  changed_when: false

- name: Display document
  ansible.builtin.debug:
    msg: "{{ get_result.stdout | from_json }}"
```

**By criteria** — look up the document without needing to capture an ObjectId first:

```yaml
- name: Fetch feature status document by criteria
  ansible.builtin.command:
    cmd: >-
      mas-devops-feature-status-update get
      --region {{ mas_region }}
      --instance-id {{ mas_instance_id }}
      --account {{ mas_account }}
      --cluster {{ mas_cluster }}
      --subscription-id {{ mas_subscription_id }}
      --type allow-list
  register: get_result
  changed_when: false

- name: Display document
  ansible.builtin.debug:
    msg: "{{ get_result.stdout | from_json }}"
```

### Using `DEVOPS_MONGO_URI`

Set `DEVOPS_MONGO_URI` once (e.g. in `group_vars/all.yml` or a `block` `environment:`). All sub-commands read it automatically — no connection flag is required on any task:

```yaml
- name: Feature status tasks
  environment:
    DEVOPS_MONGO_URI: "mongodb://{{ mas_mongo_user }}:{{ mas_mongo_password }}@{{ mas_mongo_host }}:{{ mas_mongo_port }}/admin?tls=true&tlsAllowInvalidCertificates=true"  # pragma: allowlist secret
  block:
    - name: status-update
      ansible.builtin.command:
        cmd: >-
          mas-devops-feature-status-update status-update
          --region us-east-2
          --instance-id inst02
          --account fyre-noble10-dev
          --cluster noble10
          --subscription-id sub-id01
          --type allow-list
          --feature-details '{"ips": ["2405:201:d000:9062::/64"]}'
          --status ACTIVE
          --status-details '{"message": "Allow list is active.", "request_configuration": "2405:201:d000:9062::/64"}'
```

---

## MongoDB Query Reference

Every query is a standalone `mongosh` command — replace `mongodb://localhost:27017` with your connection URL.

---

### `instance_level_config` queries

#### Fetch a specific instance document (full)

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.findOne({
    subscription_id: "sub-id01",
    account:         "fyre-noble10-dev",
    region:          "us-east-2",
    cluster:         "noble10",
    instance:        "inst02"
  })'
```

#### Fetch just the feature entries for an instance

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.findOne(
    {
      subscription_id: "sub-id01",
      account:  "fyre-noble10-dev",
      region:   "us-east-2",
      cluster:  "noble10",
      instance: "inst02"
    },
    { _id: 0, instance_level_features: 1 }
  )'
```

#### Fetch a single feature entry for an instance (`$elemMatch`)

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.findOne(
    {
      subscription_id: "sub-id01",
      account:  "fyre-noble10-dev",
      region:   "us-east-2",
      cluster:  "noble10",
      instance: "inst02"
    },
    { _id: 0, instance_level_features: { $elemMatch: { type: "allow-list" } } }
  )'
```

#### All instances for an account

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.find(
    { account: "fyre-noble10-dev" },
    { _id: 0, region: 1, cluster: 1, instance: 1, subscription_id: 1 }
  ).sort({ cluster: 1, instance: 1 }).pretty()'
```

#### All instances in a cluster

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.find(
    { account: "fyre-noble10-dev", region: "us-east-2", cluster: "noble10" },
    { _id: 0, instance: 1, subscription_id: 1 }
  ).pretty()'
```

#### All instances that have an ACTIVE allow-list feature

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.find(
    {
      "instance_level_features": {
        $elemMatch: { type: "allow-list", status: "ACTIVE" }
      }
    },
    { _id: 0, account: 1, region: 1, cluster: 1, instance: 1 }
  ).pretty()'
```

#### All instances with an IN_PROGRESS or REQUESTED feature

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.find(
    {
      "instance_level_features.status": { $in: ["REQUESTED", "IN_PROGRESS"] }
    },
    { _id: 0, account: 1, cluster: 1, instance: 1,
      instance_level_features: {
        $elemMatch: { status: { $in: ["REQUESTED", "IN_PROGRESS"] } }
      }
    }
  ).sort({ updated_at: 1 }).pretty()'
```

#### All instances with an ERROR feature

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.find(
    { "instance_level_features.status": "ERROR" },
    { _id: 0, account: 1, cluster: 1, instance: 1,
      instance_level_features: { $elemMatch: { status: "ERROR" } }
    }
  ).pretty()'
```

#### ERROR features with a specific error code

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.find(
    {
      "instance_level_features": {
        $elemMatch: { status: "ERROR", "status_details.error_code": 401 }
      }
    },
    { _id: 0, account: 1, cluster: 1, instance: 1,
      instance_level_features: {
        $elemMatch: { status: "ERROR", "status_details.error_code": 401 }
      }
    }
  ).pretty()'
```

#### Instances whose allow-list contains a specific IP/CIDR

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.find(
    {
      "instance_level_features": {
        $elemMatch: {
          type: "allow-list",
          "feature_details.ips": "2405:201:d000:9062::/64"
        }
      }
    },
    { _id: 0, account: 1, cluster: 1, instance: 1 }
  ).pretty()'
```

#### Documents updated in the last 24 hours

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.find(
    { updated_at: { $gte: new Date(Date.now() - 24 * 60 * 60 * 1000) } }
  ).sort({ updated_at: -1 }).pretty()'
```

#### Most recently updated instance documents (last 10)

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.instance_level_config.find().sort({ updated_at: -1 }).limit(10).pretty()'
```

#### Count instances per cluster

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.aggregate([
    { $group: { _id: { account: "$account", region: "$region", cluster: "$cluster" },
                count: { $sum: 1 } } },
    { $sort: { "_id.account": 1, "_id.cluster": 1 } }
  ])'
```

#### Count feature entries grouped by status (across all instances)

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.instance_level_config.aggregate([
    { $unwind: "$instance_level_features" },
    { $group: { _id: "$instance_level_features.status", count: { $sum: 1 } } },
    { $sort: { count: -1 } }
  ])'
```

#### Distinct accounts

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.instance_level_config.distinct("account")'
```

#### Distinct clusters for a region

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.instance_level_config.distinct("cluster", { region: "us-east-2" })'
```

---

### `cluster_level_config` queries

#### Fetch a specific cluster document

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.cluster_level_config.findOne({
    account: "fyre-noble10-dev",
    region:  "us-east-2",
    cluster: "noble10"
  })'
```

#### All clusters for an account

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.cluster_level_config.find(
    { account: "fyre-noble10-dev" },
    { _id: 0, region: 1, cluster: 1 }
  ).sort({ region: 1, cluster: 1 }).pretty()'
```

#### Clusters that have at least one cluster-level feature

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.cluster_level_config.find(
    { "cluster_level_features.0": { $exists: true } },
    { _id: 0, account: 1, region: 1, cluster: 1 }
  ).pretty()'
```

#### Count cluster documents per account

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.cluster_level_config.aggregate([
    { $group: { _id: "$account", count: { $sum: 1 } } },
    { $sort: { count: -1 } }
  ])'
```
