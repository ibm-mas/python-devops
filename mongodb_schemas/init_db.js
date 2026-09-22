// =============================================================================
// init_db.js — Bootstrap script for the feature_dashboard database
// Database:   feature_dashboard
//
// Initialises all collections and their indexes:
//   • cluster_level_config  — cluster-scoped feature entries
//   • instance_level_config — instance-scoped allowlisting entries
//
// Usage (mongosh):
//   mongosh "mongodb://<host>:27017/feature_dashboard" init_db.js
//
// Usage (legacy mongo shell):
//   mongo "mongodb://<host>:27017/feature_dashboard" init_db.js
// =============================================================================

const scriptDir = __dirname ?? (function() {
  const parts = __filename.split("/");
  parts.pop();
  return parts.join("/");
})();

load(scriptDir + "/cluster_level_config.js");
load(scriptDir + "/instance_level_config.js");

print("✅  feature_dashboard: cluster_level_config and instance_level_config collections and indexes initialized.");
