# mas-devops-feature-status-update

Writes MAS feature status records to the DevOps MongoDB (`mas_devops.feature_status` collection).

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

### Initialize the `feature_dashboard` database

Once MongoDB is running, initialize the schema and indexes from the repository root:

```bash
mongosh "mongodb://localhost:27017/feature_dashboard" mongodb_schemas/init_db.js
```

Verify the collections were created:

```bash
mongosh "mongodb://localhost:27017/feature_dashboard" --eval "db.getCollectionNames()"
# Expected: [ 'cluster_level_config', 'instance_level_config' ]
```

### Export the connection URL

Export `MAS_FEATURE_STATUS_DB_URL` so every subsequent command picks it up automatically without needing `--db-url` or `--db-details`:

```bash
export MAS_FEATURE_STATUS_DB_URL='mongodb://localhost:27017'
```

Then verify connectivity and indexes:

```bash
mas-devops-feature-status-update prep --create-indexes
```

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
mas-devops-feature-status-update prep --help
mas-devops-feature-status-update status-update --help
mas-devops-feature-status-update get --help
```

---

## Sub-commands

### `prep`

Verifies MongoDB connectivity and confirms that the required indexes exist on the collection.

| Index name             | Fields                                  |
|------------------------|-----------------------------------------|
| `instance_config_level` | `region` + `instance_id` + `account`  |
| `cluster_config_level`  | `region` + `cluster` + `account`      |

Pass `--create-indexes` to create missing indexes automatically instead of exiting with an error.

**Options**

| Flag | Required | Description |
|------|----------|-------------|
| `--db-details JSON` | No† | JSON object with `url` and optional `credentials` keys |
| `--db-url URL` | No† | MongoDB connection URL (alternative to `--db-details`) |
| `--create-indexes` | No | Create missing indexes automatically |

† At least one of `--db-details`, `--db-url`, or the `MAS_FEATURE_STATUS_DB_URL` environment variable is required.

**Examples**

```bash
# Verify using a db-details JSON blob (local MongoDB, no auth)
mas-devops-feature-status-update prep \
    --db-details '{"url": "mongodb://localhost:27017"}'

# Verify using a db-details JSON blob (with credentials)
mas-devops-feature-status-update prep \
    --db-details '{"url": "mongodb://localhost:27017", "credentials": {"username": "user", "password": "pass -- pragma: allowlist secret", "authSource": "admin"}}'

# Verify and auto-create missing indexes
mas-devops-feature-status-update prep \
    --db-url mongodb://localhost:27017 \
    --create-indexes
```

After a successful `prep` run the command prints the `export` statements needed to reuse the connection details in subsequent `status-update` calls.

---

### `status-update`

Upserts a feature status document.  
Upsert key: `(region, instance_id, account, cluster, type)` — an existing document is updated in-place; a new document is inserted if no match is found.

**Identity options** *(all required)*

| Flag | Description |
|------|-------------|
| `--region` | AWS region (e.g. `us-east-2`) |
| `--instance-id` | MAS instance ID (e.g. `inst02`) |
| `--account` | GitOps account name (e.g. `fyre-noble10-dev`) |
| `--cluster` | GitOps cluster name (e.g. `noble10`) |
| `--subscription-id` | Subscription ID |

**Feature options** *(all required)*

| Flag | Description |
|------|-------------|
| `--type` | Feature type (e.g. `allow-list`) |
| `--feature-details JSON` | Type-specific JSON payload. `allow-list` requires an `ips` array. |

**Status options** *(all required)*

| Flag | Description |
|------|-------------|
| `--status` | One of `REQUESTED`, `IN_PROGRESS`, `ACTIVE`, `ERROR` |
| `--status-details JSON` | JSON object describing the outcome (see schema below) |

**Timestamp options** *(all optional, default: current UTC time)*

| Flag | Description |
|------|-------------|
| `--deployment-start ISO-8601` | Start of the deployment |
| `--deployment-end ISO-8601` | End of the deployment |
| `--created-at ISO-8601` | Overrides `created_at` on document insert only |
| `--updated-at ISO-8601` | Overrides `updated_at` |

**Database connection options** *(one required)*

| Flag | Description |
|------|-------------|
| `--db-details JSON` | JSON object with `url` and optional `credentials` keys |
| `--db-url URL` | MongoDB connection URL |

**`--status-details` schema**

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

*ACTIVE* — deployment completed successfully.
```json
{
  "message": "Allow list is active.",
  "request_configuration": "2405:201:d000:9062::/64"
}
```

*ERROR* — deployment failed.
```json
{
  "message": "sample error message",
  "error_code": 401,
  "error_source": {
    "gitops_version": "8.6.0",
    "filename": "cis_ip_allowlist.yml",
    "line_no": 148,
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

# ACTIVE status — record successful completion
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

# ERROR status — record a failed deployment
mas-devops-feature-status-update status-update \
    --region us-east-2 \
    --instance-id inst02 \
    --account fyre-noble10-dev \
    --cluster noble10 \
    --subscription-id sub-id01 \
    --type allow-list \
    --feature-details '{"ips": ["2405:201:d000:9062::/64"]}' \
    --status ERROR \
    --status-details '{
      "message": "sample error message",
      "error_code": 401,
      "error_source": {
        "gitops_version": "8.6.0",
        "filename": "cis_ip_allowlist.yml",
        "line_no": 148,
        "log_file": "/var/log/gitops/run-001.log",
        "stacktrace": "Traceback (most recent call last): ..."
      },
      "request_configuration": "2405:201:d000:9060::/64"
    }' \
    --deployment-start 2026-09-11T11:48:42+00:00 \
    --deployment-end   2026-09-11T11:53:10+00:00
```

---

### `get`

Fetches a single feature status document by its ObjectId and prints it as formatted JSON.

**Arguments**

| Argument | Required | Description |
|----------|----------|-------------|
| `OBJECT_ID` | Yes | 24-character hex ObjectId (printed by `status-update` on success) |
| `--db-details JSON` | No† | JSON object with `url` and optional `credentials` keys |
| `--db-url URL` | No† | MongoDB connection URL |

† At least one of `--db-details`, `--db-url`, or the `MAS_FEATURE_STATUS_DB_URL` environment variable is required.

**Example**

```bash
mas-devops-feature-status-update get 6ab0e70ee6d3a31faa808547
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

Setting these avoids repeating `--db-details` / `--db-url` on every call.

| Variable | Description |
|----------|-------------|
| `MAS_FEATURE_STATUS_DB_URL` | MongoDB connection URL |
| `MAS_FEATURE_STATUS_DB_CREDENTIALS` | JSON object with optional `username`, `password`, `authSource`, `tls` keys |

**Precedence** (highest to lowest): `--db-details` → `--db-url` → environment variables.

```bash
export MAS_FEATURE_STATUS_DB_URL='mongodb://user:pass@host:27017' #pragma: allowlist secret
export MAS_FEATURE_STATUS_DB_CREDENTIALS='{"username": "u", "password": "p"}' #pragma: allowlist secret

mas-devops-feature-status-update status-update \
    --region us-east-2 \
    ...
```

---

## Database Setup

The `feature_dashboard` MongoDB database must be initialised before this tool can write records. It holds two collections:

| Collection | Cardinality |
|---|---|
| `cluster_level_config` | One document per `tenant_id × account × region × cluster` |
| `instance_level_config` | One document per `tenant_id × subscription_id × account × region × cluster × instance` |

### Initialize

Run `init_db.js` (which loads both schema files) against your MongoDB host:

```bash
# mongosh (≥ 1.x, recommended)
mongosh "mongodb://<host>:27017/feature_dashboard" mongodb_schemas/init_db.js

# Legacy mongo shell
mongo "mongodb://<host>:27017/feature_dashboard" mongodb_schemas/init_db.js
```

Or initialize each collection individually:

```bash
mongosh "mongodb://<host>:27017/feature_dashboard" mongodb_schemas/cluster_level_config.js
mongosh "mongodb://<host>:27017/feature_dashboard" mongodb_schemas/instance_level_config.js
```

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

> **Note:** `drop()` removes the collection, all documents, and all indexes. Re-run `init_db.js` to recreate them.

### Indexes created by `init_db.js`

**`cluster_level_config`**

| Index name | Fields | Unique |
|---|---|---|
| `ux_cluster_level_config_tenant_account_region_cluster` | `tenant_id, account, region, cluster` | ✓ |
| `ix_cluster_level_config_tenant_account` | `tenant_id, account` | |

**`instance_level_config`**

| Index name | Fields | Unique |
|---|---|---|
| `ux_instance_level_config_tenant_sub_account_region_cluster_instance` | `tenant_id, subscription_id, account, region, cluster, instance` | ✓ |
| `ix_instance_level_config_tenant_sub_account_region_cluster` | `tenant_id, subscription_id, account, region, cluster` | |
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

Collection: `mas_devops.feature_status`

```json
{
  "_id": "<ObjectId>",
  "schema_version": 1,
  "region": "us-east-2",
  "instance_id": "inst02",
  "account": "fyre-noble10-dev",
  "cluster": "noble10",
  "subscription_id": "sub-id01",
  "type": "allow-list",
  "feature_details": { "ips": ["2405:201:d000:9062::/64"] },
  "status": "ACTIVE",
  "status_details": { "message": "...", "request_configuration": "..." },
  "deployment_start": "<ISODate>",
  "deployment_end": "<ISODate>",
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

### Minimal task — `prep`

Verify connectivity before any write. Use `--create-indexes` on first run.

```yaml
- name: Verify MongoDB connectivity and indexes
  ansible.builtin.command:
    cmd: >-
      mas-devops-feature-status-update prep
      --db-url {{ mas_mongo_url }}
      --create-indexes
  register: prep_result
  changed_when: "'Creating missing indexes' in prep_result.stdout"
```

### Minimal task — `status-update`

```yaml
- name: Upsert feature status (ACTIVE)
  ansible.builtin.command:
    cmd: >-
      mas-devops-feature-status-update status-update
      --db-url {{ mas_mongo_url }}
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

### Minimal task — `get`

Extract the document ID from `status-update` output and fetch the written document:

```yaml
- name: Extract document ID
  ansible.builtin.set_fact:
    mas_document_id: >-
      {{ status_update_result.stdout
         | regex_search('Document ID: ([a-f0-9]{24})', '\1')
         | first }}

- name: Fetch feature status document
  ansible.builtin.command:
    cmd: >-
      mas-devops-feature-status-update get
      --db-url {{ mas_mongo_url }}
      {{ mas_document_id }}
  register: get_result
  changed_when: false

- name: Display document
  ansible.builtin.debug:
    msg: "{{ get_result.stdout | from_json }}"
```

### Using environment variables instead of `--db-url`

Set `MAS_FEATURE_STATUS_DB_URL` once (e.g. in `group_vars/all.yml` or a `block` `environment:`) to avoid repeating the flag on every task:

```yaml
- name: Feature status tasks
  environment:
    MAS_FEATURE_STATUS_DB_URL: "mongodb://localhost:27017"
  block:
    - name: prep
      ansible.builtin.command:
        cmd: mas-devops-feature-status-update prep --create-indexes

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

### By document ID

```bash
mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.feature_status.findOne({ _id: ObjectId("<doc_id>") })'
```

---

### By identity fields

```bash
# Full identity match (region + instance + account + cluster + type)
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.findOne({
    region:      "us-east-2",
    instance_id: "inst02",
    account:     "fyre-noble10-dev",
    cluster:     "noble10",
    type:        "allow-list"
  })'

# All documents for a specific instance
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find(
    { account: "fyre-noble10-dev", instance_id: "inst02" }
  ).sort({ updated_at: -1 }).pretty()'

# All documents for a cluster (all instances within it)
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find(
    { account: "fyre-noble10-dev", cluster: "noble10" }
  ).sort({ updated_at: -1 }).pretty()'

# All documents for an account across all clusters
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find(
    { account: "fyre-noble10-dev" }
  ).sort({ cluster: 1, instance_id: 1 }).pretty()'

# All documents for a region
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find(
    { region: "us-east-2" }
  ).sort({ account: 1, cluster: 1 }).pretty()'

# All documents for a subscription ID
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find(
    { subscription_id: "sub-id01" }
  ).sort({ updated_at: -1 }).pretty()'
```

---

### By status

```bash
# All documents in a specific status
mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.feature_status.find({ status: "ACTIVE" }).pretty()'

mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.feature_status.find({ status: "ERROR" }).pretty()'

mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.feature_status.find({ status: "IN_PROGRESS" }).pretty()'

mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.feature_status.find({ status: "REQUESTED" }).pretty()'

# Multiple statuses at once
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find(
    { status: { $in: ["REQUESTED", "IN_PROGRESS"] } }
  ).sort({ updated_at: 1 }).pretty()'

# Count documents grouped by status
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.aggregate([
    { $group: { _id: "$status", count: { $sum: 1 } } },
    { $sort:  { count: -1 } }
  ])'
```

---

### By feature type and payload

```bash
# All allow-list documents
mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.feature_status.find({ type: "allow-list" }).pretty()'

# ACTIVE allow-list entries for a specific IP/CIDR
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find({
    type:   "allow-list",
    status: "ACTIVE",
    "feature_details.ips": "2405:201:d000:9062::/64"
  }).pretty()'

# Any allow-list document whose IP array contains a given prefix (regex)
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find({
    type: "allow-list",
    "feature_details.ips": { $regex: "^2405:201:" }
  }).pretty()'
```

---

### By error details

```bash
# All ERROR documents with a specific HTTP error code
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find({
    status: "ERROR",
    "status_details.error_code": 401
  }).pretty()'

# ERROR documents mentioning a keyword in the message (case-insensitive)
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find({
    status: "ERROR",
    "status_details.message": { $regex: "timeout", $options: "i" }
  }).pretty()'

# ERROR documents from a specific GitOps version
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find({
    status: "ERROR",
    "status_details.error_source.gitops_version": "8.6.0"
  }).pretty()'
```

---

### By time

```bash
# Documents updated in the last 24 hours
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find({
    updated_at: { $gte: new Date(Date.now() - 24 * 60 * 60 * 1000) }
  }).sort({ updated_at: -1 }).pretty()'

# Documents created in a specific date range
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find({
    created_at: {
      $gte: new Date("2026-09-01T00:00:00Z"),
      $lte: new Date("2026-09-30T23:59:59Z")
    }
  }).sort({ created_at: -1 }).pretty()'

# Deployments that took longer than 5 minutes
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find({
    deployment_start: { $exists: true },
    deployment_end:   { $exists: true },
    $expr: {
      $gte: [
        { $dateDiff: {
            startDate: { $dateFromString: { dateString: "$deployment_start" } },
            endDate:   { $dateFromString: { dateString: "$deployment_end" } },
            unit: "minute"
        }},
        5
      ]
    }
  }).pretty()'

# Most recently updated documents (last 10)
mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.feature_status.find().sort({ updated_at: -1 }).limit(10).pretty()'
```

---

### Projection — select specific fields only

```bash
# Identity + status summary (no feature payload)
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find(
    { account: "fyre-noble10-dev" },
    { region: 1, instance_id: 1, cluster: 1, subscription_id: 1,
      type: 1, status: 1, updated_at: 1, _id: 0 }
  ).sort({ updated_at: -1 }).pretty()'

# Status and timestamps only
mongosh "mongodb://localhost:27017/mas_devops" --eval '
  db.feature_status.find(
    { cluster: "noble10" },
    { status: 1, deployment_start: 1, deployment_end: 1, updated_at: 1, _id: 0 }
  ).pretty()'
```

---

### Counting and diagnostics

```bash
# Total document count
mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.feature_status.countDocuments()'

# Count for a specific account + status
mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.feature_status.countDocuments({ account: "fyre-noble10-dev", status: "ACTIVE" })'

# All distinct accounts
mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.feature_status.distinct("account")'

# All distinct clusters for a region
mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.feature_status.distinct("cluster", { region: "us-east-2" })'

# All distinct statuses present
mongosh "mongodb://localhost:27017/mas_devops" --eval \
  'db.feature_status.distinct("status")'
```
