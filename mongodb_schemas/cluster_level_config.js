// =============================================================================
// Collection: cluster_level_config
// Database:   feature_dashboard
// Purpose:    Stores cluster-scoped feature entries. Each document represents
//             one cluster within a region/account/tenant and holds the list of
//             cluster-level features enabled for that cluster (e.g. 'dro').
//
//             Split from allowlisting_config: cluster_level_features[] was
//             previously embedded inside the deep
//               account → regions[] → clusters[] hierarchy.
//             Flattening to one document per cluster simplifies writes and
//             allows targeted index coverage without touching instance data.
//
// Document cardinality:
//   ONE document per (tenant_id × account × region × cluster).
// =============================================================================

db.createCollection("cluster_level_config", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenant_id", "account", "region", "cluster",
        "cluster_level_features", "created_at", "updated_at"
      ],
      additionalProperties: false,
      properties: {

        // ------------------------------------------------------------------
        // Document identity
        // ------------------------------------------------------------------
        _id: {
          bsonType: "objectId",
          description: "MongoDB-generated document identifier."
        },
        tenant_id: {
          bsonType: "string",
          description: "Tenant/customer identifier. All customer-scoped queries MUST filter on this field. This is the multi-tenancy isolation key."
        },
        account: {
          bsonType: "string",
          description: "Account identifier as returned by the cluster polling mechanism."
        },
        region: {
          bsonType: "string",
          description: "Cloud/geographic region identifier. Example: 'us-east-1'."
        },
        cluster: {
          bsonType: "string",
          description: "Cluster name or identifier as returned by the cluster polling mechanism."
        },

        // ------------------------------------------------------------------
        // Cluster-level features (e.g. dro)
        // ------------------------------------------------------------------
        cluster_level_features: {
          bsonType: "array",
          description: "List of cluster-scoped feature entries. Each element represents one feature enabled at the cluster level (e.g. 'dro').",
          minItems: 0,
          items: {
            bsonType: "object",
            additionalProperties: true
          }
        },

        // ------------------------------------------------------------------
        // Document-level audit timestamps
        // ------------------------------------------------------------------
        created_at: {
          bsonType: "date",
          description: "UTC timestamp when this document was first created."
        },
        updated_at: {
          bsonType: "date",
          description: "UTC timestamp of the most recent modification to this document."
        }

      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});

// ---------------------------------------------------------------------------
// Indexes
// ---------------------------------------------------------------------------

// Compound unique index — enforces the one-document-per
// (tenant × account × region × cluster) invariant
db.cluster_level_config.createIndex(
  { tenant_id: 1, account: 1, region: 1, cluster: 1 },
  { unique: true, name: "ux_cluster_level_config_tenant_account_region_cluster" }
);

// Index for querying all clusters for a given tenant + account
db.cluster_level_config.createIndex(
  { tenant_id: 1, account: 1 },
  { name: "ix_cluster_level_config_tenant_account" }
);

