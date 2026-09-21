# MongoDB Schemas — `feature_dashboard`

MongoDB validator scripts for the `feature_dashboard` database.
Extracted from [`allowlisting-tdd.md`](../allowlisting-tdd.md) §7.

## Collections

The original `allowlisting_config` collection has been split into two flat collections — one per level of the hierarchy — to enable targeted writes and precise index coverage.

| File | Collection | Cardinality | Description |
|---|---|---|---|
| [`cluster_level_config.js`](cluster_level_config.js) | `cluster_level_config` | 1 doc per `(tenant_id × account × region × cluster)` | Cluster-scoped feature entries (e.g. `dro`). |
| [`instance_level_config.js`](instance_level_config.js) | `instance_level_config` | 1 doc per `(tenant_id × account × region × cluster × instance)` | Instance-scoped IP/CIDR allowlisting entries with per-feature deployment lifecycle state. |
| [`init_db.js`](init_db.js) | *(all)* | — | Bootstrap runner — initialises both collections and all indexes. |

### Key fields per collection

**`cluster_level_config`**

| Field | Type | Notes |
|---|---|---|
| `tenant_id` | string | Multi-tenancy isolation key |
| `account` | string | Account from cluster polling |
| `region` | string | e.g. `us-east-1` |
| `cluster` | string | Cluster name from polling |
| `cluster_level_features[]` | array | One element per cluster-level feature (e.g. `dro`) |

**`instance_level_config`**

| Field | Type | Notes |
|---|---|---|
| `tenant_id` | string | Multi-tenancy isolation key |
| `account` | string | Account from cluster polling |
| `region` | string | e.g. `us-east-1` |
| `cluster` | string | Cluster name from polling |
| `instance` | string | Specific instance within the cluster |
| `instance_level_features[]` | array | One element per feature — holds `allow_lists.ips[]`, `source`, `cluster_poll_status`, timestamps, audit fields |

## Files

| File | Collection | Description |
|---|---|---|
| [`cluster_level_config.js`](cluster_level_config.js) | `cluster_level_config` | Cluster-scoped feature entries. |
| [`instance_level_config.js`](instance_level_config.js) | `instance_level_config` | Instance-scoped IP/CIDR allowlisting entries. |
| [`init_db.js`](init_db.js) | *(all)* | Bootstrap runner — initialises all collections and indexes. |

---

## Query reference

All queries assume `use feature_dashboard` has been run first. Replace
`<tenant>`, `<account>`, `<region>`, `<cluster>`, `<instance>`, and
`<feature_key>` with real values.

---

### `cluster_level_config` queries

#### List all cluster documents

```js
db.cluster_level_config.find().pretty()
```

#### List all clusters for a tenant

```js
db.cluster_level_config.find(
  { tenant_id: "<tenant>" },
  { _id: 0, account: 1, region: 1, cluster: 1 }
).pretty()
```

#### List all clusters for an account

```js
db.cluster_level_config.find(
  { tenant_id: "<tenant>", account: "<account>" },
  { _id: 0, region: 1, cluster: 1 }
).pretty()
```

#### List all clusters in a region

```js
db.cluster_level_config.find(
  { tenant_id: "<tenant>", account: "<account>", region: "<region>" },
  { _id: 0, cluster: 1 }
).pretty()
```

#### Fetch a single cluster document

```js
db.cluster_level_config.findOne({
  tenant_id: "<tenant>",
  account:   "<account>",
  region:    "<region>",
  cluster:   "<cluster>"
})
```

#### List cluster-level features for a specific cluster

```js
db.cluster_level_config.findOne(
  { tenant_id: "<tenant>", account: "<account>", region: "<region>", cluster: "<cluster>" },
  { _id: 0, cluster_level_features: 1 }
)
```

#### Find all clusters that have a specific cluster-level feature enabled

```js
db.cluster_level_config.find(
  {
    tenant_id: "<tenant>",
    "cluster_level_features.feature_key": "<feature_key>"
  },
  { _id: 0, account: 1, region: 1, cluster: 1, cluster_level_features: 1 }
).pretty()
```

#### Find all clusters that have any cluster-level feature enabled (non-empty array)

```js
db.cluster_level_config.find(
  { tenant_id: "<tenant>", "cluster_level_features.0": { $exists: true } },
  { _id: 0, account: 1, region: 1, cluster: 1 }
).pretty()
```

#### Find all clusters with no cluster-level features

```js
db.cluster_level_config.find(
  { tenant_id: "<tenant>", cluster_level_features: { $size: 0 } },
  { _id: 0, account: 1, region: 1, cluster: 1 }
).pretty()
```

#### Count clusters per region (for a tenant)

```js
db.cluster_level_config.aggregate([
  { $match: { tenant_id: "<tenant>" } },
  { $group: { _id: { account: "$account", region: "$region" }, cluster_count: { $sum: 1 } } },
  { $sort: { "_id.account": 1, "_id.region": 1 } }
])
```

#### Count clusters per account (for a tenant)

```js
db.cluster_level_config.aggregate([
  { $match: { tenant_id: "<tenant>" } },
  { $group: { _id: "$account", cluster_count: { $sum: 1 } } },
  { $sort: { _id: 1 } }
])
```

---

### `instance_level_config` queries

#### List all instance documents

```js
db.instance_level_config.find().pretty()
```

#### List all instances for a tenant

```js
db.instance_level_config.find(
  { tenant_id: "<tenant>" },
  { _id: 0, account: 1, region: 1, cluster: 1, instance: 1 }
).pretty()
```

#### List all instances for an account

```js
db.instance_level_config.find(
  { tenant_id: "<tenant>", account: "<account>" },
  { _id: 0, region: 1, cluster: 1, instance: 1 }
).pretty()
```

#### List all instances in a region

```js
db.instance_level_config.find(
  { tenant_id: "<tenant>", account: "<account>", region: "<region>" },
  { _id: 0, cluster: 1, instance: 1 }
).pretty()
```

#### List all instances in a cluster

```js
db.instance_level_config.find(
  { tenant_id: "<tenant>", account: "<account>", region: "<region>", cluster: "<cluster>" },
  { _id: 0, instance: 1 }
).pretty()
```

#### Fetch a single instance document (full detail)

```js
db.instance_level_config.findOne({
  tenant_id: "<tenant>",
  account:   "<account>",
  region:    "<region>",
  cluster:   "<cluster>",
  instance:  "<instance>"
})
```

#### Fetch only the instance-level features for a specific instance

```js
db.instance_level_config.findOne(
  {
    tenant_id: "<tenant>",
    account:   "<account>",
    region:    "<region>",
    cluster:   "<cluster>",
    instance:  "<instance>"
  },
  { _id: 0, instance_level_features: 1 }
)
```

#### Fetch a single feature entry for a specific instance

Returns just the matching element from `instance_level_features[]` using `$elemMatch`.

```js
db.instance_level_config.findOne(
  {
    tenant_id: "<tenant>",
    account:   "<account>",
    region:    "<region>",
    cluster:   "<cluster>",
    instance:  "<instance>"
  },
  {
    _id: 0,
    instance_level_features: {
      $elemMatch: { feature_key: "<feature_key>" }
    }
  }
)
```

#### Find all instances that have a specific feature key

```js
db.instance_level_config.find(
  {
    tenant_id: "<tenant>",
    "instance_level_features.feature_key": "<feature_key>"
  },
  { _id: 0, account: 1, region: 1, cluster: 1, instance: 1 }
).pretty()
```

#### Find all instances for a feature key — include the matching feature entry only

```js
db.instance_level_config.find(
  {
    tenant_id: "<tenant>",
    "instance_level_features.feature_key": "<feature_key>"
  },
  {
    _id: 0,
    account: 1, region: 1, cluster: 1, instance: 1,
    instance_level_features: { $elemMatch: { feature_key: "<feature_key>" } }
  }
).pretty()
```

#### Find all instances that have any non-empty allow list for a feature

```js
db.instance_level_config.find(
  {
    tenant_id: "<tenant>",
    instance_level_features: {
      $elemMatch: {
        feature_key: "<feature_key>",
        "allow_lists.ips": { $exists: true, $not: { $size: 0 } }
      }
    }
  },
  { _id: 0, account: 1, region: 1, cluster: 1, instance: 1 }
).pretty()
```

#### Find all instances whose allow list contains a specific IP or CIDR

```js
db.instance_level_config.find(
  {
    tenant_id: "<tenant>",
    instance_level_features: {
      $elemMatch: {
        feature_key: "<feature_key>",
        "allow_lists.ips": "<ip_or_cidr>"
      }
    }
  },
  { _id: 0, account: 1, region: 1, cluster: 1, instance: 1 }
).pretty()
```

#### Find all stale instances (poll status = stale or unreachable)

```js
db.instance_level_config.find(
  {
    tenant_id: "<tenant>",
    "instance_level_features.cluster_poll_status": { $in: ["stale", "unreachable"] }
  },
  { _id: 0, account: 1, region: 1, cluster: 1, instance: 1,
    instance_level_features: {
      $elemMatch: { cluster_poll_status: { $in: ["stale", "unreachable"] } }
    }
  }
).pretty()
```

#### Find all instances not polled since a given timestamp

```js
db.instance_level_config.find(
  {
    tenant_id: "<tenant>",
    "instance_level_features.cluster_last_polled_at": {
      $lt: ISODate("<YYYY-MM-DDTHH:MM:SSZ>")
    }
  },
  { _id: 0, account: 1, region: 1, cluster: 1, instance: 1 }
).pretty()
```

#### Find all instances never polled (cluster_last_polled_at absent)

```js
db.instance_level_config.find(
  {
    tenant_id: "<tenant>",
    "instance_level_features.cluster_last_polled_at": { $exists: false }
  },
  { _id: 0, account: 1, region: 1, cluster: 1, instance: 1 }
).pretty()
```

---

### Cross-collection queries

#### List all distinct regions for an account

```js
// From cluster_level_config (one query covers all clusters, hence all regions)
db.cluster_level_config.distinct("region", {
  tenant_id: "<tenant>",
  account:   "<account>"
})
```

#### List all distinct accounts for a tenant

```js
db.cluster_level_config.distinct("account", { tenant_id: "<tenant>" })
```

#### List all distinct clusters in a region

```js
db.cluster_level_config.distinct("cluster", {
  tenant_id: "<tenant>",
  account:   "<account>",
  region:    "<region>"
})
```

#### List all distinct instances in a cluster

```js
db.instance_level_config.distinct("instance", {
  tenant_id: "<tenant>",
  account:   "<account>",
  region:    "<region>",
  cluster:   "<cluster>"
})
```

#### Full cluster view — cluster features + all instances (aggregation join)

Joins `cluster_level_config` and `instance_level_config` for a single cluster
using `$lookup`.

```js
db.cluster_level_config.aggregate([
  {
    $match: {
      tenant_id: "<tenant>",
      account:   "<account>",
      region:    "<region>",
      cluster:   "<cluster>"
    }
  },
  {
    $lookup: {
      from:         "instance_level_config",
      localField:   "cluster",
      foreignField: "cluster",
      let: {
        t: "$tenant_id",
        a: "$account",
        r: "$region",
        c: "$cluster"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenant_id", "$$t"] },
                { $eq: ["$account",   "$$a"] },
                { $eq: ["$region",    "$$r"] },
                { $eq: ["$cluster",   "$$c"] }
              ]
            }
          }
        },
        { $project: { _id: 0, instance: 1, instance_level_features: 1 } }
      ],
      as: "instances"
    }
  },
  {
    $project: {
      _id: 0,
      account: 1, region: 1, cluster: 1,
      cluster_level_features: 1,
      instances: 1
    }
  }
])
```

#### Count instances per cluster across all clusters for a tenant

```js
db.instance_level_config.aggregate([
  { $match: { tenant_id: "<tenant>" } },
  {
    $group: {
      _id: { account: "$account", region: "$region", cluster: "$cluster" },
      instance_count: { $sum: 1 }
    }
  },
  { $sort: { "_id.account": 1, "_id.region": 1, "_id.cluster": 1 } }
])
```

#### Count instances per region for an account

```js
db.instance_level_config.aggregate([
  { $match: { tenant_id: "<tenant>", account: "<account>" } },
  { $group: { _id: "$region", instance_count: { $sum: 1 } } },
  { $sort: { _id: 1 } }
])
```

---

## Running

### Initialize the collections

```bash
mongosh "mongodb://<host>:27017/feature_dashboard" mongodb_schemas/init_db.js
```

### Clear the collections

```js
use feature_dashboard
db.cluster_level_config.deleteMany({})
db.instance_level_config.deleteMany({})
```

### Drop the collections

```js
use feature_dashboard
db.cluster_level_config.drop()
db.instance_level_config.drop()
```

> **Note:** `drop()` removes the collection, all its documents, and its indexes. Re-run `init_db.js` to recreate them.

### Run a schema file directly

```bash
mongosh "mongodb://<host>:27017/feature_dashboard" mongodb_schemas/cluster_level_config.js
mongosh "mongodb://<host>:27017/feature_dashboard" mongodb_schemas/instance_level_config.js
```

---

## Validation behaviour

Both collections use:

```js
validationLevel: "strict"   // enforced on inserts AND updates
validationAction: "error"   // rejects non-conforming writes outright
```

`additionalProperties: false` is set on every top-level object and nested object (except `cluster_level_features[]` items, which allow extension fields) to prevent undocumented fields from being silently stored.
