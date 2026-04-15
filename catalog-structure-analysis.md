# Catalog Structure Analysis: v9-260216-amd64.yaml vs. Subsequent Releases

## Executive Summary

This analysis compares the structure of [`v9-260216-amd64.yaml`](src/mas/devops/data/catalogs/v9-260216-amd64.yaml) (baseline) against subsequent catalog files to identify properties that were added in the February 16, 2026 release but were not carried forward to later releases.

**Analysis Date:** April 15, 2026
**Baseline File:** v9-260216-amd64.yaml
**Comparison Files:** v9-260226, v9-260305, v9-260313, v9-260318, v9-260326, v9-260414

---

## Key Findings

### 1. Missing Property: `datarefinery_version`

**Status:** ❌ **MISSING in all subsequent releases**

**Baseline (v9-260216):**
```yaml
# Line 42
datarefinery_version: 11.0.0+20250513.203727.232
```

**Context from baseline file (lines 38-42):**
```yaml
# TODO: Why is this here, but commented out?
# datarefinery_build: +20240517.202103.146

# I have added this as a guess as to the actual version used, we are currently using the wsl_version, but that does not exist for datarefinery
# See: https://ibm-mas.slack.com/archives/C02PUHKQB5L/p1770849370378689
datarefinery_version: 11.0.0+20250513.203727.232
```

**Impact:** This property was explicitly added to address a known issue where `wsl_version` was being used for Data Refinery, but Data Refinery doesn't have a WSL version. The Slack reference indicates this was a deliberate fix.

**Subsequent files:** All files from v9-260226 onwards only have the commented-out `datarefinery_build` line and do NOT include the `datarefinery_version` property.

---

## Detailed Comparison

### Properties Present in v9-260216 (Baseline)

The baseline file contains the following structure with **comprehensive documentation**:

#### Cloud Pak for Data Dependencies Section
```yaml
# Dependencies - Cloud Pak for Data
# -----------------------------------------------------------------------------
cpd_product_version_default: 5.2.0

ibm_licensing_version: 4.2.17
common_svcs_version: 4.13.0
common_svcs_version_1: 4.11.0
cp4d_platform_version: 5.2.0+20250709.170324
ibm_zen_version: 6.2.0+20250530.152516.232
wsl_version: 11.0.0+20250521.202913.73
wsl_runtimes_version: 11.0.0+20250515.090949.21
wml_version: 11.0.0+20250530.193146.282
spark_version: 11.0.0+20250604.163055.2097
cognos_version: 28.0.0+20250515.175459.10054

postgress_version: 5.16.0+20250827.110911.2626
ccs_build: 11.0.0+20250605.130237.468
ccs_extras_version: 11.0.0

elasticsearch_version: 1.1.2667
opensearch_version: 1.1.2494

datarefinery_version: 11.0.0+20250513.203727.232  # ⚠️ MISSING IN LATER FILES

events_version: 5.0.1
```

#### Db2u Dependencies Section
```yaml
# Dependencies - Db2u
# -----------------------------------------------------------------------------
db2u_version: 7.3.1+20250821.161005.16793
db2u_extras_version: 1.0.6
db2u_filter: db2
db2_channel_default: v110509.0
```

#### Other Dependencies
```yaml
# Dependencies - CouchDb
couchdb_version: 1.0.13

# Dependencies - Minio
minio_version: RELEASE.2025-06-13T11-33-47Z

# Dependencies - MongoDB
mongo_extras_version_default: 8.0.17
mongo_extras_version_4: 4.4.21
mongo_extras_version_5: 5.0.23
mongo_extras_version_6: 6.0.12
mongo_extras_version_7: 7.0.23
mongo_extras_version_8: 8.0.17

# Dependencies - Amlen
amlen_extras_version: 1.1.3

# Dependencies - Suite License Service
sls_version: 3.12.5

# Dependencies - Truststore Manager
tsm_version: 1.7.2

# Dependencies - Data Dictionary
dd_version: 1.1.21
```

### Structural Changes in Subsequent Files

Starting with **v9-260226**, the file structure was reorganized:

1. **Section headers were simplified** - removed detailed subsection comments
2. **Properties were reordered** - dependencies are no longer grouped by product category
3. **New properties were added:**
   - `uds_version: 2.0.12`
   - `uds_extras_version: 1.5.0`
   - `appconnect_version: 6.2.0`

4. **The `datarefinery_version` property was removed** despite the baseline having explicit documentation about why it was needed

---

## Comparison Table: Property Presence

| Property | v9-260216 | v9-260226+ | Notes |
|----------|-----------|------------|-------|
| `datarefinery_version` | ✅ Present | ❌ Missing | **Critical: Explicitly added to fix WSL version issue** |
| `uds_version` | ❌ Missing | ✅ Present | New in v9-260226 |
| `uds_extras_version` | ❌ Missing | ✅ Present | New in v9-260226 |
| `appconnect_version` | ❌ Missing | ✅ Present | New in v9-260226 |
| Section organization | Detailed | Simplified | Structure changed |
| TODO comments | Multiple | Fewer | Documentation reduced |

---

## Documentation Quality Comparison

### v9-260216 (Baseline) - Rich Documentation
The baseline file includes:
- **Detailed section headers** for each dependency category
- **Inline comments** explaining version choices
- **TODO comments** highlighting areas needing attention
- **External references** (GitHub links, Slack conversations)
- **Explicit reasoning** for property additions

Example:
```yaml
# Dependencies - Cloud Pak for Data
# -----------------------------------------------------------------------------
cpd_product_version_default: 5.2.0

ibm_licensing_version: 4.2.17                    # Operator version 4.2.14 (https://github.com/IBM/cloud-pak/tree/master/repo/case/ibm-licensing)
common_svcs_version: 4.13.0                      # Operator version 4.13.0 (https://github.com/IBM/cloud-pak/tree/master/repo/case/ibm-cp-common-services)
common_svcs_version_1: 4.11.0                    # TODO: Do we really still need to mirror two different versions of common services?  If so, why?
```

### v9-260226+ - Simplified Documentation
Later files have:
- **Generic section header** ("Dependencies")
- **Fewer inline comments**
- **Less context** about version choices
- **Minimal TODO comments**

Example:
```yaml
# Dependencies
# -----------------------------------------------------------------------------
ibm_licensing_version: 4.2.17                # Operator version 4.2.14 (https://github.com/IBM/cloud-pak/tree/master/repo/case/ibm-licensing)
common_svcs_version: 4.13.0                  # Operator version 4.13.0 (https://github.com/IBM/cloud-pak/tree/master/repo/case/ibm-cp-common-services)
common_svcs_version_1: 4.11.0                  # Additional version 4.11.0
```

---

## Recommendations

### 1. Restore `datarefinery_version` Property (HIGH PRIORITY)

**Action Required:** Add `datarefinery_version` back to all catalog files from v9-260226 onwards.

**Rationale:**
- The baseline file explicitly documents why this property was added
- It addresses a known issue where WSL version was incorrectly used for Data Refinery
- The Slack reference indicates this was a deliberate architectural decision
- Removing it may cause Data Refinery mirroring issues

**Suggested Implementation:**
```yaml
# After line 40 in subsequent files, add:
datarefinery_version: 11.0.0+20250513.203727.232  # Data Refinery version (see v9-260216 for context)
```

### 2. Restore Documentation Context (MEDIUM PRIORITY)

**Action Required:** Restore the detailed section headers and TODO comments from v9-260216.

**Rationale:**
- The baseline file contains valuable context about version choices
- TODO comments highlight areas needing attention
- External references (GitHub, Slack) provide traceability
- Future maintainers will benefit from this documentation

**Suggested Sections to Restore:**
```yaml
# Dependencies - Cloud Pak for Data
# -----------------------------------------------------------------------------

# Dependencies - Db2u
# -----------------------------------------------------------------------------

# Dependencies - CouchDb
# -----------------------------------------------------------------------------

# Dependencies - Minio
# -----------------------------------------------------------------------------

# Dependencies - MongoDB
# -----------------------------------------------------------------------------

# Dependencies - Amlen
# -----------------------------------------------------------------------------

# Dependencies - Suite License Service
# -----------------------------------------------------------------------------

# Dependencies - Truststore Manager
# -----------------------------------------------------------------------------

# Dependencies - Data Dictionary
# -----------------------------------------------------------------------------
```

### 3. Establish Property Tracking Process (MEDIUM PRIORITY)

**Action Required:** Create a process to track property additions/removals across catalog versions.

**Suggested Approach:**
1. Maintain a "catalog schema" document listing all valid properties
2. Require justification for property removals
3. Use automated diff checking between catalog versions
4. Document breaking changes in release notes

### 4. Review TODO Comments (LOW PRIORITY)

The baseline file contains several TODO comments that should be addressed:

```yaml
# Line 20: TODO: Do we really still need to mirror two different versions of common services?
# Line 33: TODO: If this is only used in CPD 5.1.3, we shouldn't need this in this catalog metadata file
# Line 37: TODO: Why is this here, but commented out?
# Line 44: TODO: Why is this here, there is no evidence that it is being used in image mirroring?
# Line 70: TODO: We probably don't need to keep carrying forward the now unsupported versions
# Line 158: TODO: What is this?  It almost certainly should not be here.
```

---

## Impact Assessment

### Critical Impact
- **`datarefinery_version` removal:** May cause Data Refinery mirroring to fail or use incorrect versions

### Medium Impact
- **Documentation loss:** Makes maintenance harder for future developers
- **Context loss:** Removes rationale for version choices

### Low Impact
- **Section reorganization:** Cosmetic change, but reduces readability

---

## Conclusion

The v9-260216-amd64.yaml file introduced important structural improvements and the critical `datarefinery_version` property. However, subsequent releases (v9-260226 onwards) did not carry forward this property, potentially reintroducing the issue it was meant to solve.

**Primary Action Item:** Restore `datarefinery_version` to all catalog files from v9-260226 onwards to maintain consistency with the baseline structure and prevent potential Data Refinery mirroring issues.

---

## Appendix: File Versions Analyzed

| File | Date | Status |
|------|------|--------|
| v9-260216-amd64.yaml | Feb 16, 2026 | ✅ Baseline (correct structure) |
| v9-260226-amd64.yaml | Feb 26, 2026 | ❌ Missing `datarefinery_version` |
| v9-260305-amd64.yaml | Mar 5, 2026 | ❌ Missing `datarefinery_version` |
| v9-260313-amd64.yaml | Mar 13, 2026 | ❌ Missing `datarefinery_version` |
| v9-260318-amd64.yaml | Mar 18, 2026 | ❌ Missing `datarefinery_version` |
| v9-260326-amd64.yaml | Mar 26, 2026 | ❌ Missing `datarefinery_version` |
| v9-260414-amd64.yaml | Apr 14, 2026 | ❌ Missing `datarefinery_version` |

---

**Generated:** April 15, 2026
**Analyst:** Bob (Planning Mode)