# OLM Manual Approval Support — Phase 1: Core Approval Primitives

> Part 1 of 3. Related plans:
> [Phase 2 — Namespace Awareness & Pause Support](2026-11-15-olm-manual-approvals-phase2-namespace-pause-support.md)
> [Phase 3 — Guided Approval Workflow](2026-11-15-olm-manual-approvals-phase3-guided-approval-workflow.md)

## Objective

Extract and generalize the inlined InstallPlan approval/wait logic in `applySubscription` into
reusable, individually-testable primitives, so that the wider automation (ansible-devops playbooks,
tekton pipelines) can create subscriptions with `installPlanApproval: Manual` and interact with
pending InstallPlans as first-class operations.

This phase is a refactor-plus-primitives change: **no behavior change by default**. It is the
foundation for namespace-level "pause" support (Phase 2) and the guided approval workflow
(Phase 3).

## Background — Current State

[`src/mas/devops/olm.py`](../../src/mas/devops/olm.py) has partial manual-approval support, but it
is narrow and implicit:

- `applySubscription` accepts `installPlanApproval="Manual"` but **requires** a `startingCSV`
  (olm.py:177) and auto-approves only the *initial* InstallPlan to reach that CSV
  (olm.py:331-346). "Manual" today really means "pin to startingCSV, self-approve once".
- After install it returns as soon as `installedCSV == startingCSV` even when the subscription is
  in `UpgradePending` — there is no way to represent "an upgrade is now waiting for a human".
- There are no standalone primitives to **list** pending InstallPlans, **approve** one, or
  **wait** for one to complete — the approve/wait logic is inlined inside `applySubscription`.
- All wait loops are infinite `sleep(30)` polls with no timeout parameter.
- Subscription template: [`src/mas/devops/templates/subscription.yml.j2`](../../src/mas/devops/templates/subscription.yml.j2)
  already renders `installPlanApproval` and `startingCSV` when set — no template change needed.
- In-repo callers of `getSubscription` are read-only channel lookups
  ([suite.py:275](../../src/mas/devops/mas/suite.py#L275),
  [apps.py:218](../../src/mas/devops/mas/apps.py#L218),
  [aiservice.py:145](../../src/mas/devops/aiservice.py#L145)).
  `applySubscription` itself is called only from tests in this repo — the real consumers are
  external (ansible-devops, pipeline repos).

### OLM mechanics reference

- A Subscription with `spec.installPlanApproval: Manual` generates InstallPlans with
  `status.phase: RequiresApproval`.
- Approving = merge-patch `spec.approved: true` on the InstallPlan.
- After approval: phase → `Installing` → `Complete`; CSV installs;
  `subscription.status.installedCSV` updates; `subscription.status.state` returns to
  `AtLatestKnown` until the next update appears (`UpgradePending` while one is pending).
- InstallPlans may also reach `status.phase: Failed` (check `status.conditions` for detail).
- The correct InstallPlan for a subscription may not carry the label selector
  (`operators.coreos.com/<package>.<namespace>`) — the ownership fallback via
  `metadata.ownerReferences` already exists in `applySubscription` and must be preserved
  (see [test_olm_installplan_selection.py](../../test/src/test_olm_installplan_selection.py)).

## Critical Rules

- Maintain backward compatibility: existing `applySubscription` call sites (including external
  consumers in ansible-devops and pipeline repos) must behave identically unless they opt in to
  new parameters.
- All existing tests must pass without modification.
- Default approval behavior remains exactly as today: `installPlanApproval="Manual"` +
  `startingCSV` set → initial InstallPlan auto-approved, function returns at
  `installedCSV == startingCSV`.
- Every new wait-style function takes an explicit `timeout` and raises on expiry — no infinite
  loops in new code.
- All new approval operations must be idempotent (approving an already-approved or Complete
  InstallPlan is a no-op, not an error).
- Validate with `black` and `flake8` after each code change.
- Update copyright headers where files are modified.
- Docstrings must follow the project docstring rules in `.bob/rules/python/docstrings.md`.

## Open Decisions (to be made before/during implementation)

- [ ] **Return types for new primitives**: raw kubernetes-client resource objects vs plain
  dicts vs dataclasses. Plain dicts (or a small dataclass) are friendlier for pipeline/CLI
  consumption and for Jinja2 rendering in notifications; raw resources preserve consistency with
  the rest of the module. Recommendation: dicts with documented keys for the list/describe
  functions, raw resources only for approve/get single-resource functions.
- [ ] **Timeout exception type**: reuse `OLMException` with a message vs introduce a dedicated
  `OLMTimeoutError` (subclass of `OLMException` so existing `except OLMException` handlers still
  catch it). Recommendation: dedicated subclass.
- [ ] **`onApprovalRequired` callback signature** for `applySubscription` (see task 2.2):
  called with what context — (namespace, packageName, installPlan) or a richer status dict?
  Should the callback be able to veto/abort, or is it informational only?
- [ ] **Poll interval configurability**: fixed `sleep(30)` vs parameter with default. Existing
  code hardcodes 30s; new functions should accept `pollInterval` with default 30 for
  consistency. Confirm.
- [ ] **Naming**: keep everything in `olm.py` (module is already ~400 lines) vs new
  `src/mas/devops/olm_approval.py` with re-exports from `olm.py` for import compatibility.
  Recommendation: keep in `olm.py` unless it grows unwieldy; the project favors flat module
  organization.

## Execution Plan

### Phase 1: New primitives in `olm.py`

- [ ] **1.1** `getSubscriptionApprovalMode(dynClient, namespace, packageName) -> str`
  - Read `spec.installPlanApproval` from the subscription; return `"Automatic"` when unset
    (OLM default); return `None` when the subscription doesn't exist.
- [ ] **1.2** `getPendingInstallPlans(dynClient, namespace=None) -> list[dict]`
  - List all InstallPlans with `status.phase == "RequiresApproval"`, optionally scoped to a
    namespace.
  - Enrich each entry with: `name`, `namespace`, `subscription` (resolved via
    ownerReferences, falling back to label selector), `package`, `csvNames`
    (`spec.clusterServiceVersionNames`), `creationTimestamp`.
  - This is the data source for guidance UI, CLI listing, and Slack notifications later.
- [ ] **1.3** `getPendingInstallPlan(dynClient, namespace, packageName) -> dict | None`
  - Convenience wrapper: the pending InstallPlan for one subscription, using the same
    label-selector-then-ownership resolution order as `applySubscription`.
- [ ] **1.4** `approveInstallPlan(dynClient, namespace, installPlanName) -> InstallPlan`
  - Merge-patch `spec.approved: true` (content type `application/merge-patch+json`, matching
    the existing patch at olm.py:339-344).
  - Idempotent: fetch first; no-op (log + return) if already approved or Complete.
- [ ] **1.5** `waitForInstallPlanComplete(dynClient, namespace, installPlanName, timeout, pollInterval=30)`
  - Poll phase until `Complete`; raise timeout error on expiry; raise `OLMException` on
    `Failed` phase (include `status.conditions` detail in the message).
- [ ] **1.6** `waitForSubscriptionStable(dynClient, namespace, packageName, timeout, pollInterval=30, targetCSV=None)`
  - Wait for `status.state == "AtLatestKnown"`, or `UpgradePending` with
    `status.installedCSV == targetCSV` when a target CSV is supplied (mirrors the existing
    logic at olm.py:354-378 but bounded).

### Phase 2: Refactor `applySubscription`

- [ ] **2.1** Replace the inlined InstallPlan-selection/approval/wait blocks
  (olm.py:256-378) with calls to the new primitives. Behavior must be unchanged for existing
  parameter combinations — the existing tests in
  [test_olm.py](../../test/src/test_olm.py) and
  [test_olm_installplan_selection.py](../../test/src/test_olm_installplan_selection.py) are
  the regression gate.
- [ ] **2.2** Add `onApprovalRequired` parameter to `applySubscription`:
  - `"wait"` (default, current behavior: poll forever),
  - `"return"`: return the subscription together with a structured pending-approval result
    (see Phase 2 plan for the shape),
  - or a callable invoked when an InstallPlan enters `RequiresApproval`.
  - This is the seam the wider automation will use; final semantics decided under the Open
    Decisions above.
- [ ] **2.3** Relax the Manual/`startingCSV` coupling:
  - Add `autoApproveInitialInstall: bool` (default `None` = current implicit behavior:
  auto-approve when Manual + startingCSV set, for backward compatibility).
  - When `autoApproveInitialInstall=False`, Manual + startingCSV no longer self-approves and
  Manual without startingCSV is no longer rejected — instead the function relies on
  `onApprovalRequired` semantics.
  - Keep the `OLMException` for the legacy combination only if no new-style parameter is
  supplied, so external callers see no change until they opt in.

### Phase 3: Tests

- [ ] **3.1** New `test/src/test_olm_approvals.py` following the mocked-DynamicClient pattern
  in [test_olm_installplan_selection.py](../../test/src/test_olm_installplan_selection.py)
  (`MockResource` / `MockResourceList` helpers — consider extracting them to a shared
  helper module if duplication gets excessive).
  - `getSubscriptionApprovalMode`: unset spec → Automatic; explicit Manual; missing subscription.
  - `getPendingInstallPlans`: filters by phase; namespace scoping; enrichment via
    ownerReferences vs label selector; empty result.
  - `approveInstallPlan`: patches with merge-patch content type; no-op when already
    approved/Complete.
  - `waitForInstallPlanComplete`: Complete within timeout; timeout expiry raises; Failed
    phase raises with condition detail.
  - `waitForSubscriptionStable`: AtLatestKnown; UpgradePending with matching target CSV;
    timeout expiry.
- [ ] **3.2** Regression: `make test` passes with existing tests unmodified.
- [ ] **3.3** New tests for refactored `applySubscription` opt-in paths:
  - `onApprovalRequired="return"` returns pending state instead of blocking.
  - `autoApproveInitialInstall=False` does not patch the InstallPlan.

## Deliverables

- Reusable primitives in [`src/mas/devops/olm.py`](../../src/mas/devops/olm.py)
- Refactored `applySubscription` with opt-in approval interaction modes
- Comprehensive unit tests in `test/src/test_olm_approvals.py`
- No breaking changes for external consumers

## Out of Scope (handled in later phases)

- Namespace-scoped status aggregation and pause semantics → Phase 2
- Ordered approval plans, CLI tool, Slack integration → Phase 3
