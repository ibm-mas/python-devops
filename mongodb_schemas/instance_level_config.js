// =============================================================================
// Collection: instance_level_config
// Database:   feature_dashboard
// Purpose:    Stores instance-scoped feature entries. Each document represents
//             one instance within a cluster/region/account/tenant and holds the
//             list of per-feature state for that instance (IP/CIDR lists,
//             deployment lifecycle, audit metadata, etc.).
//
//             Split from allowlisting_config: instance_level_features[] was
//             previously embedded at the deepest leaf of the
//               account → regions[] → clusters[] → instances[] hierarchy.
//             Flattening to one document per instance enables efficient
//             targeted upserts by ansible-devops and GitHub webhook writes,
//             precise index coverage for status detection, and independent
//             scaling of cluster and instance data.
//
// Document cardinality:
//   ONE document per (tenant_id × subscription_id × account × region × cluster × instance).
//
// instance_level_features item shape (flattened — no nested allow_lists[]):
//
//   SUCCESS scenario
//   ----------------
//   {
//     type: "allow-list",
//     feature_details: { ips: ["2405:201:d000:9062::/64"] },
//     status: "ACTIVE",
//     status_details: {
//       message: "Allow list is active.",
//       request_configuration: "2405:201:d000:9062::/64"
//     },
//     deployment_start: "2026-09-11T11:48:42.863523+00:00",
//     deployment_end:   "2026-09-11T11:48:42.863523+00:00",
//     source:     "admin_ui",
//     created_at: ISODate(...),
//     updated_at: ISODate(...)
//   }
//
//   FAILURE scenario
//   ----------------
//   {
//     type: "allow-list",
//     feature_details: { ips: ["2405:201:d000:9062::/64"] },
//     status: "ERROR",
//     status_details: {
//       message: "sample error message",
//       error_code: 401,
//       error_source: {
//         gitops_version: "8.6.0",
//         filename:      "...",
//         line_no:        1,
//         log_file:      "...",
//         stacktrace:    "..."
//       },
//       request_configuration: "2405:201:d000:9060::/64"
//     },
//     deployment_start: "2026-09-11T11:48:42.863523+00:00",
//     deployment_end:   "2026-09-11T11:48:42.863523+00:00",
//     source:     "admin_ui",
//     created_at: ISODate(...),
//     updated_at: ISODate(...)
//   }
// =============================================================================

db.createCollection("instance_level_config", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenant_id", "subscription_id", "account", "region",
        "cluster", "instance", "instance_level_features", "created_at", "updated_at"
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
        subscription_id: {
          bsonType: "string",
          description: "Subscription identifier associated with the tenant/instance. Example: 'sub-id01'."
        },
        account: {
          bsonType: "string",
          description: "Account identifier as returned by the cluster polling mechanism."
        },
        region: {
          bsonType: "string",
          description: "Cloud/geographic region identifier. Example: 'us-east-2'."
        },
        cluster: {
          bsonType: "string",
          description: "Cluster name or identifier as returned by the cluster polling mechanism."
        },
        instance: {
          bsonType: "string",
          description: "Specific instance identifier within the cluster."
        },

        // ------------------------------------------------------------------
        // Instance-level features — one entry per deployed feature
        // ------------------------------------------------------------------
        instance_level_features: {
          bsonType: "array",
          description: "List of feature-level entries for this instance. Each element represents one deployed feature (e.g. allow-list) with its full deployment lifecycle state.",
          minItems: 0,
          items: {
            bsonType: "object",
            required: [
              "type", "feature_details", "status",
              "source", "created_at", "updated_at"
            ],
            additionalProperties: false,
            properties: {

              // Feature type discriminator
              type: {
                bsonType: "string",
                enum: ["allow-list"],
                description: "Feature type. Determines the shape of feature_details. Currently only 'allow-list' is supported."
              },

              // ---- feature payload ----------------------------------------
              feature_details: {
                bsonType: "object",
                description: "Feature-specific configuration payload. Shape depends on 'type'.",
                required: ["ips"],
                additionalProperties: false,
                properties: {
                  ips: {
                    bsonType: "array",
                    description: "List of IPv4/IPv6 addresses or CIDR ranges to allowlist. Example: ['2405:201:d000:9060::/64', '10.0.0.0/8'].",
                    minItems: 1,
                    items: {
                      bsonType: "string",
                      description: "A single IPv4/IPv6 address or CIDR range."
                    }
                  }
                }
              },

              // ---- deployment lifecycle ------------------------------------
              status: {
                bsonType: "string",
                enum: ["REQUESTED", "IN_PROGRESS", "ACTIVE", "ERROR"],
                description: "Deployment lifecycle state of this feature entry."
              },

              status_details: {
                bsonType: "object",
                description: "Additional context for the current status. Present for ACTIVE and ERROR; may be omitted for REQUESTED/IN_PROGRESS.",
                additionalProperties: false,
                properties: {

                  message: {
                    bsonType: "string",
                    description: "Human-readable status message. ACTIVE: confirmation text. ERROR: error description."
                  },

                  // ERROR-only fields
                  error_code: {
                    bsonType: "int",
                    description: "Numeric HTTP/application error code. Set only when status = ERROR. Example: 401."
                  },
                  error_source: {
                    bsonType: "object",
                    description: "Machine-readable origin of the error. Set only when status = ERROR.",
                    additionalProperties: false,
                    properties: {
                      gitops_version: {
                        bsonType: "string",
                        description: "GitOps toolchain version that processed this entry. Example: '8.6.0'."
                      },
                      filename: {
                        bsonType: "string",
                        description: "Source filename in the GitOps pipeline where the error originated."
                      },
                      line_no: {
                        bsonType: "int",
                        description: "Line number within 'filename' where the error was raised."
                      },
                      log_file: {
                        bsonType: "string",
                        description: "Path or reference to the log file capturing the error output."
                      },
                      stacktrace: {
                        bsonType: "string",
                        description: "Full stacktrace string captured at the point of failure."
                      }
                    }
                  },

                  // Common field for ACTIVE and ERROR
                  request_configuration: {
                    bsonType: "string",
                    description: "Verbatim echo of the originally submitted IP/CIDR value that was processed. Aids reconciliation when the applied value differs from what was requested."
                  }

                }
              },

              deployment_start: {
                bsonType: "string",
                description: "ISO-8601 timestamp set when the deployment pipeline begins processing this feature entry (status → IN_PROGRESS)."
              },
              deployment_end: {
                bsonType: "string",
                description: "ISO-8601 timestamp set when the pipeline completes, whether successfully (ACTIVE) or with failure (ERROR). Null while the pipeline is still running."
              },

              // ---- audit ---------------------------------------------------
              source: {
                bsonType: "string",
                enum: ["ansible_devops", "github_webhook", "cluster_poll", "admin_ui"],
                description: "The system that last wrote this feature entry. Used for audit traceability and reconciliation."
              },
              created_at: {
                bsonType: "date",
                description: "UTC timestamp when this feature entry was first created."
              },
              updated_at: {
                bsonType: "date",
                description: "UTC timestamp of the most recent modification to this feature entry."
              }

            } // end instance_level_features item properties
          }   // end instance_level_features items
        },    // end instance_level_features array

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
// (tenant × subscription × account × region × cluster × instance) invariant
db.instance_level_config.createIndex(
  { tenant_id: 1, subscription_id: 1, account: 1, region: 1, cluster: 1, instance: 1 },
  { unique: true, name: "ux_instance_level_config_tenant_sub_account_region_cluster_instance" }
);

// Index for ansible-devops / GitHub webhook upserts — primary lookup path
db.instance_level_config.createIndex(
  { tenant_id: 1, subscription_id: 1, account: 1, region: 1, cluster: 1 },
  { name: "ix_instance_level_config_tenant_sub_account_region_cluster" }
);

// Multikey index on feature status — supports finding all documents with
// at least one entry in a given lifecycle state (e.g. IN_PROGRESS or ERROR)
db.instance_level_config.createIndex(
  { "instance_level_features.status": 1 },
  { name: "ix_instance_level_config_feature_status" }
);

// Sparse index for error triage — only indexes documents that have at least
// one ERROR entry; avoids index bloat for the common ACTIVE/non-error case
db.instance_level_config.createIndex(
  { "instance_level_features.status_details.error_code": 1 },
  { sparse: true, name: "ix_instance_level_config_error_code" }
);
