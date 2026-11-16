# OLM Manual Approval Support — Phase 1: Core Approval Primitives

> Part 1 of 3. Related plans:
> [Phase 2 — Namespace Awareness & Pause Support](2026-11-15-olm-manual-approvals-phase2-namespace-pause-support.md)
> [Phase 3 — Guided Approval Workflow](2026-11-15-olm-manual-approvals-phase3-guided-approval-workflow.md)

## Status (updated 2026-11-16 — COMPLETE, pending commit)

**Phase 1 is finished: `olm.py` implementation plus `test/src/test_olm_approvals.py`, all
validated on branch `manualsubs` (work started on `unpublishedcats`).**

- All 33 new tests in [test_olm_approvals.py](../../test/src/test_olm_approvals.py) pass, plus
  the 5 InstallPlan-selection regression tests (38 total, via WSL).
- Full unit suite (`pytest test/src -m "not openshift"`): 435 passed, 4 skipped. The only
  failures are `test_slack.py` (`SLACK_TOKEN is not set` — environmental, unrelated to this
  change, pre-existing).
- `black` and `flake8` clean on both files.
- `test_olm.py` (openshift-marked integration) not run — no cluster available.

Next step: commit, then Phase 2
([namespace pause support](2026-11-15-olm-manual-approvals-phase2-namespace-pause-support.md)).

### What has been implemented in `olm.py`

- Module docstring added; imports extended (`from time import sleep, time`,
  `from typing import Callable, Optional, Union`).
- `OLMTimeoutError(OLMException)` exception class.
- New public primitives (inserted between `getSubscription` and `applySubscription`):
  - `getSubscriptionApprovalMode(dynClient, namespace)` — namespace-scoped; raises on mixed
    modes; returns `None` for empty namespace; treats unset `spec.installPlanApproval` as
    `"Automatic"`.
  - `getPendingInstallPlans(dynClient, namespace=None)` — filters phase `RequiresApproval`;
    enriches via `_describePendingInstallPlan`; caches subscription list per namespace.
  - `getPendingInstallPlan(dynClient, namespace, packageName)` — label-selector first, then
    ownership fallback over all InstallPlans in the namespace.
  - `approveInstallPlan(dynClient, namespace, installPlanName)` — idempotent merge-patch of
    `spec.approved = true`; no-op when already approved/Complete; raises on `Failed` phase.
  - `waitForInstallPlanComplete(dynClient, namespace, installPlanName, timeout=None, pollInterval=30)`
    — polls to `Complete`; raises `OLMException` on `Failed`, `OLMTimeoutError` on expiry;
    `timeout=None` waits indefinitely.
  - `waitForSubscriptionStable(dynClient, namespace, packageName, timeout=None, pollInterval=30, targetCSV=None)`
    — `AtLatestKnown`, or `UpgradePending` with `installedCSV == targetCSV`; resolves the
    subscription via `getSubscription` first.
- Private helpers:
  - `_describePendingInstallPlan(installPlanResource, subscriptions)` — the normalized
    approval-info dict (keys: `installPlan`, `namespace`, `subscription`, `package`,
    `csvNames`, `currentCSV`, `targetCSV`, `created`). Subscription resolved via
    ownerReferences first, then the `operators.coreos.com/<package>.<namespace>` label
    (package parsed by stripping the trailing `.<namespace>` suffix).
  - `_validateNamespaceApprovalConsistency(dynClient, namespace, packageName, installPlanApproval)`
    — lists subscriptions, excludes the one being applied (by `spec.name` or
    `metadata.name`), raises naming conflicting subscriptions.
  - `_shouldReleaseForApproval(onApprovalRequired, approvalInfo)` — for `"return"` always
    True; for a callable, releases when the callable returns `False`.
- `applySubscription` new parameters: `autoApproveInitialInstall: Optional[bool] = None`,
  `onApprovalRequired: Union[str, Callable] = "wait"`, `pollInterval: int = 30`.
  - Validation order: (1) `autoApproveInitialInstall` requires Manual; (2) `onApprovalRequired`
    must be `"wait"`, `"return"` or callable; (3) legacy raise (Manual without startingCSV)
    only when no new-style opt-in; (4) namespace-consistency validation **only when
    `installPlanApproval` is explicitly set AND new-style opt-in** (see discovery below).
  - InstallPlan wait loop: auto-approve (via `approveInstallPlan`) only when Manual +
    startingCSV + `autoApproveInitialInstall is not False` + CSV match + not already
    approved; otherwise `onApprovalRequired != "wait"` releases the caller with a
    `(subscription, approvalInfo)` tuple (point A: InstallPlan `RequiresApproval`).
  - Subscription wait loop: `UpgradePending` + Manual + `installedCSV == startingCSV` →
    normal return (legacy); `UpgradePending` blocked before target → release path via
    `getPendingInstallPlan` (point B; if no pending plan resolves, logs a warning and keeps
    waiting).
  - Docstring rewritten in Google style (Args/Returns/Raises) per
    `.bob/rules/python/docstrings.md`.
- `deleteSubscription` and everything else untouched.

### Key implementation-time discovery — OLM dependency subscriptions

[test_olm.py:58](../../test/src/test_olm.py#L58) documents that installing `ibm-sls` makes
OLM auto-create the `ibm-truststore-mgr` Subscription **in the same namespace** (typically
with default Automatic approval). So real MAS namespaces CAN legitimately contain a mix of
modes, and namespace-consistency validation applied unconditionally would break the existing
`installPlanApproval="Manual" + startingCSV` flow (the repo's own integration test
`test_crud_with_manual_approval_and_starting_csv`). Resolution: validation in
`applySubscription` runs **only for new-style callers** (when `autoApproveInitialInstall` is
set or `onApprovalRequired != "wait"`), preserving the backward-compat critical rule.
`getSubscriptionApprovalMode` still raises on a mix unconditionally — this tension needs a
Phase 2 decision (e.g. whether OLM-created dependency subscriptions should be exempt).

### Environment notes for resuming

- Tests/lint run under **WSL** (Ubuntu-24.04): the repo `.venv` is a Linux venv
  (`.venv/bin/activate`), and `make test` / `make lint` use it. Windows PowerShell python
  (`C:\Users\097891866\.venv`) has no pytest. Use e.g.
  `wsl -e bash -c "cd /mnt/c/Users/097891866/Documents/GitHub/ibm-mas/python-devops && . .venv/bin/activate && python -m pytest test/src/test_olm_approvals.py test/src/test_olm_installplan_selection.py -v"`.
  Verified working: the WSL venv has pytest 9.0.2 and flake8 7.3.0. **black was not installed**
  and was added with `pip install black` (26.10.1) — it is not in the repo's dev extras, so a
  fresh `make install` will not provide it.
- [test_olm.py](../../test/src/test_olm.py) is cluster-integration (`pytest.mark.openshift`,
  needs a real cluster) — the regression gate for unit work is
  [test_olm_installplan_selection.py](../../test/src/test_olm_installplan_selection.py) plus
  the new test file.
- `.flake8`: `extend-ignore = E501, E203, D`, `max-line-length = 160`.
- `make lint` runs flake8 with `--select=E9,F63,F7,F82` (syntax/undefined-name only) plus an
  advisory pass; pre-commit config exists (`.pre-commit-config.yaml`).

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
- **Approval mode scope (verified against OLM docs, Nov 2026):** `spec.installPlanApproval`
  is set **per Subscription**. OLM does not enforce namespace-level consistency — mixing
  Manual and Automatic subscriptions within one namespace is technically possible and the
  OLM documentation says nothing prohibiting it.
  However, this library treats approval mode as a **namespace property by convention**:
  InstallPlans are namespace-scoped, the pause/awareness semantics we are building are
  namespace-oriented (Phase 2), and MAS automation is overwhelmingly
  one-subscription-per-namespace (`mas-{id}-core`, `mas-{id}-{appId}`, `aiservice-{id}`).
  The namespace-scoped accessor below therefore raises on a mixed namespace rather than
  trying to represent a mix.

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

## Decisions (resolved during implementation, 2026-11-15)

- [x] **Return types for new primitives**: dicts for the list/describe functions
  (`getPendingInstallPlans` / `getPendingInstallPlan` / approval-info in `applySubscription`
  release path, all produced by `_describePendingInstallPlan`), raw resources for
  `approveInstallPlan` / `waitForInstallPlanComplete` / `waitForSubscriptionStable` returns.
- [x] **Timeout exception type**: dedicated `OLMTimeoutError(OLMException)` subclass, so
  existing `except OLMException` handlers still catch timeouts.
- [x] **`onApprovalRequired` callback signature**: the callable receives the approval-info
  dict (same shape as `getPendingInstallPlans` entries) as its sole argument; returning
  `False` releases the caller from the wait (same as `"return"` mode); any other return
  value continues waiting. Implemented in `_shouldReleaseForApproval`.
- [x] **Poll interval configurability**: `pollInterval=30` parameter on all new wait
  functions and on `applySubscription`.
- [x] **Naming**: everything kept in `olm.py`.
- [x] **Namespace with no subscriptions**: `getSubscriptionApprovalMode` returns `None`.
- [x] **Mixed-mode exception severity**: `getSubscriptionApprovalMode` raises
  `OLMException` naming the conflicting subscriptions.
- [x] **`applySubscription` namespace validation**: implemented as fail-fast, but **only
  for new-style callers** (explicit `installPlanApproval` + `autoApproveInitialInstall` set
  or `onApprovalRequired != "wait"`) — see the dependency-subscription discovery above for
  why unconditional validation would break the legacy flow. "Explicit override" is simply
  omitting `installPlanApproval` (no validation runs, preserving current behavior of not
  touching the mode of an existing subscription).
- [x] **Timeout semantics**: `timeout=None` (default) waits indefinitely on the new wait
  primitives — required so the refactored `applySubscription` preserves its legacy
  unbounded waits; callers who want bounded waits pass an explicit value.

## Execution Plan

### Phase 1: New primitives in `olm.py` — COMPLETE (untested)

- [x] **1.1** `getSubscriptionApprovalMode(dynClient, namespace) -> str`
  - **Namespace-scoped**: list all Subscriptions in the namespace and read each
    `spec.installPlanApproval` (treating unset as `"Automatic"`, the OLM default).
  - If all subscriptions agree, return the namespace's effective mode (`"Automatic"` or
    `"Manual"`).
  - If the namespace contains a **mix** of modes, raise `OLMException` naming the
    conflicting subscriptions — mixing is technically possible in OLM but unsupported by
    this library's namespace-scoped model (see mechanics note above).
  - Empty namespace returns `None`.
- [x] **1.2** `getPendingInstallPlans(dynClient, namespace=None) -> list[dict]`
  - Implemented as planned; enrichment keys are `installPlan`, `namespace`, `subscription`,
    `package`, `csvNames`, `currentCSV`, `targetCSV`, `created` (superset of the plan's
    original key list, matching the Phase 2 `pendingApprovals` contract draft).
- [x] **1.3** `getPendingInstallPlan(dynClient, namespace, packageName) -> dict | None`
  - Convenience wrapper: the pending InstallPlan for one subscription, using the same
    label-selector-then-ownership resolution order as `applySubscription`.
- [x] **1.4** `approveInstallPlan(dynClient, namespace, installPlanName) -> InstallPlan`
  - Merge-patch `spec.approved: true` (content type `application/merge-patch+json`).
  - Idempotent: fetch first; no-op (log + return) if already approved or Complete.
  - Additionally raises `OLMException` on `Failed` phase (with `status.conditions` detail).
- [x] **1.5** `waitForInstallPlanComplete(dynClient, namespace, installPlanName, timeout=None, pollInterval=30)`
  - Poll phase until `Complete`; `OLMTimeoutError` on expiry; `OLMException` on `Failed`.
  - `timeout=None` (default) waits indefinitely.
- [x] **1.6** `waitForSubscriptionStable(dynClient, namespace, packageName, timeout=None, pollInterval=30, targetCSV=None)`
  - Wait for `status.state == "AtLatestKnown"`, or `UpgradePending` with
    `status.installedCSV == targetCSV` when a target CSV is supplied.
  - Raises `OLMException` when no subscription exists for the package.

### Phase 2: Refactor `applySubscription` — COMPLETE (untested)

- [x] **2.1** Approval in the InstallPlan wait loop now goes through `approveInstallPlan`;
  subscription wait and remaining loops use `pollInterval`. The InstallPlan *selection*
  logic (label selector + ownership fallback) was kept inline — it is not one of the
  primitives. Behavior is intended to be unchanged for existing parameter combinations.
- [x] **2.2** `onApprovalRequired` parameter added: `"wait"` (default) / `"return"` /
  callable. Release points: (A) InstallPlan `RequiresApproval` that we are not
  auto-approving, and (B) subscription `UpgradePending` blocked before the target CSV.
  Release returns a `(subscription, approvalInfo)` tuple — the return type of
  `applySubscription` changes **only** in opt-in modes.
- [x] **2.3** `autoApproveInitialInstall` added (None = legacy auto-approve when Manual +
  startingCSV; False disables). Manual without startingCSV is accepted **only** when a
  new-style parameter is supplied, otherwise the legacy `OLMException` is preserved
  (mirrored by integration test `test_crud_with_manual_approval` in test_olm.py).

### Phase 3: Tests — COMPLETE

- [x] **3.1** New `test/src/test_olm_approvals.py` following the mocked-DynamicClient pattern
  in [test_olm_installplan_selection.py](../../test/src/test_olm_installplan_selection.py).
  The full design worked out during implementation (mocks never touch a real cluster):

  **Mock helpers** (define fresh in the new file — `Mock()` auto-attributes mean every
  attribute the code reads via `getattr(..., default)` MUST be set explicitly, or the
  default never applies):

  ```python
  class ResourceList:            # minimal stand-in, just .items
      def __init__(self, items): self.items = items

  def makeSubscription(name, namespace, package, approval=None, state=None, installedCSV=None):
      # Mock with metadata.name/namespace, spec.name, spec.installPlanApproval,
      # status.state, status.installedCSV all set explicitly

  def makeOwnerRef(kind, name): ...   # Mock with .kind and .name

  def makeInstallPlan(name, namespace, csvNames, phase, labels=None, ownerRefs=None,
                      approved=None, created="2026-11-15T10:00:00Z"):
      # Mock with metadata.name/namespace/labels/ownerReferences/creationTimestamp,
      # spec.clusterServiceVersionNames, spec.approved, status.phase, status.conditions
      # all set explicitly (ownerRefs default [], labels may be None)

  def buildDynClient(subscriptionHandler, installPlanHandler):
      # Mock client; resources.get side_effect maps
      # ("operators.coreos.com/v1alpha1", "Subscription"|"InstallPlan") to two Mock APIs
      # whose .get side_effects are the handlers; returns (client, subAPI, ipAPI)
  ```

  Handler dispatch convention (kwargs only): `label_selector` in kwargs → subscription
  lookup by label; `name` in kwargs → single-resource get (return the resource object,
  NOT a ResourceList — `applyResource` and `_describePendingInstallPlan` expect a
  resource); otherwise → namespace listing (return ResourceList).

  **Primitive tests:**
  - `getSubscriptionApprovalMode`: unset spec → `"Automatic"`; explicit Manual; mixed
    (Manual + unset) raises `OLMException` naming both subscriptions; empty namespace →
    `None`.
  - `getPendingInstallPlans`: filters to `RequiresApproval` (mix Complete/Installing plans
    in the handler); enrichment via ownerReferences (assert all dict keys incl.
    `currentCSV` from subscription status, `targetCSV` = last of csvNames, `created`);
    label fallback (no ownerRefs, label `operators.coreos.com/<pkg>.<ns>`, subscription
    matched by `spec.name`); `namespace=None` aggregates across namespaces (sub handler
    dispatches on `kwargs.get("namespace")`).
  - `getPendingInstallPlan`: found via label selector; ownerRef fallback (label selector
    returns a Complete plan, namespace listing contains the pending one);
    `None` when no subscription / nothing pending.
  - `approveInstallPlan`: patch called once with
    `content_type="application/merge-patch+json"` and `plan.spec.approved is True` after
    the call; no patch when `approved=True` or phase `Complete`; raises on phase `Failed`.
  - `waitForInstallPlanComplete`: phase transition RequiresApproval→Complete (pop-list of
    name-get responses); `Failed` raises with conditions in message; timeout via
    `@patch("mas.devops.olm.time", side_effect=[0, 500])` + `timeout=300` →
    `OLMTimeoutError` (patch `mas.devops.olm.sleep` too).
  - `waitForSubscriptionStable`: `AtLatestKnown` returns; `UpgradePending` +
    `installedCSV == targetCSV` returns; timeout raises `OLMTimeoutError` (same time
    patching trick); no subscription → `OLMException`.

  **`applySubscription` tests** (patch `mas.devops.olm.createNamespace`,
  `ensureOperatorGroupExists`, `getPackageManifest`, `sleep`, and
  `mas.devops.olm.Environment` returning a mock env whose template.render returns a
  subscription YAML with `metadata.name: test-operator` — copy from
  test_olm_installplan_selection.py; pass `packageChannel` + `catalogSource` explicitly so
  the manifest is not consulted):

  - **Validation (no cluster mocks needed — raise before first API call, `Mock()` client):**
    - legacy: Manual without startingCSV, no opt-in → `OLMException` "startingCSV must be
      provided" (mirrors integration test test_crud_with_manual_approval).
    - `onApprovalRequired="bogus"` → `OLMException`.
    - `autoApproveInitialInstall=True` without Manual → `OLMException`.
  - **Namespace mode conflict**: sub handler namespace-listing returns another
    subscription (`spec.name` different, approval unset → Automatic); call with
    `installPlanApproval="Manual"` + `onApprovalRequired="return"` → raises "different
    approval mode". (Raises during validation, before Environment is needed.)
  - **Point A release ("return" mode)**: Manual, no startingCSV,
    `onApprovalRequired="return"`; sub handler: first label call `[]` (create path), then
    `[subscription]`; name → subscription; ip handler: label/name → pendingPlan
    (RequiresApproval, ownerRef Subscription/test-operator). Expect tuple
    `(subscription, approvalInfo)`; `approvalInfo["installPlan"]`,
    `["package"] == "test-operator"`, `["csvNames"]`; `ipAPI.patch.assert_not_called()`.
  - **Auto-approve disabled**: Manual + startingCSV matching plan csvNames +
    `autoApproveInitialInstall=False` + `"return"` → tuple returned, patch NOT called.
  - **Callback release**: `onApprovalRequired=Mock(return_value=False)` → tuple;
    callback called once with the approval-info dict.
  - **Callback continue**: `onApprovalRequired=Mock(return_value=True)`, Manual without
    startingCSV; ip name-get responses pop-list `[pendingPlan, completePlan, ...]`;
    subscription state `AtLatestKnown` → returns subscription (not a tuple), callback
    called once.
  - **Point B release**: Manual + startingCSV "v1.0.0"; label selector returns
    `[completePlan(v1.0.0, Complete), pendingUpgradePlan(v2.0.0, RequiresApproval)]`
    (both carry ownerRefs); selection picks completePlan (CSV match) → wait loop skipped;
    subscription name-get returns state `UpgradePending`, `installedCSV="v0.9.0"` →
    release via `getPendingInstallPlan` (label lookup finds pendingUpgradePlan) → tuple
    with `approvalInfo["installPlan"]` = the upgrade plan.
  - **Legacy auto-approve regression** (wait mode, default params): Manual + startingCSV;
    ip name-get pop-list `[pendingPlan, pendingPlan, completePlan, ...]` (two pendingPlan
    entries because the loop get and `approveInstallPlan`'s internal get each consume
    one); subscription `UpgradePending` with `installedCSV == startingCSV` → returns the
    subscription object itself; `ipAPI.patch.assert_called_once()` with merge-patch
    content type.

  Gotchas verified against the implementation while designing these:
  - `applyResource` calls `subAPI.get(name=...)` then `subAPI.patch(...)` — the name-get
    must return a truthy resource (Mock) so the patch path runs; patch is a Mock.
  - The namespace-consistency validation (new-style callers only) consumes a plain
    `subAPI.get(namespace=...)` listing — handlers must cover the no-label/no-name case.
  - `waitForSubscriptionStable` calls `getSubscription` (label) first, then name-gets.
  - Timeout tests patch `mas.devops.olm.time` (the module-level import
    `from time import ... time` makes it patchable).

- [x] **3.2** Regression: run via WSL (see Environment notes) —
  `python -m pytest test/src/test_olm_approvals.py test/src/test_olm_installplan_selection.py -v`
  (and the rest of the unit suite). test_olm.py is openshift-marked integration; run only
  if a cluster is available. **No existing test file may be modified.**
  Result: 38/38 pass in the two files; full unit suite 435 passed / 4 skipped, with only the
  pre-existing environmental `test_slack.py` failures (`SLACK_TOKEN is not set`).
  Implementation notes: the design held up — the only deviation was that `approveInstallPlan`
  returns the *patch result*, not the fetched resource, so the merge-patch test asserts
  `result is installPlanAPI.patch.return_value`. A `ResponseSequence` helper (pop until one
  item remains, then repeat it) replaced the raw pop-lists for name-get phase transitions,
  and `applySubscriptionIsolation` is a `@contextmanager` (not a fixture) wrapping the
  createNamespace/ensureOperatorGroupExists/getPackageManifest/sleep/Environment patches.
  `getPackageManifest` is patched with `return_value=None` so an accidental manifest lookup
  fails loudly instead of silently auto-Mocking.
- [x] **3.3** Lint/format: `black src/mas/devops/olm.py test/src/test_olm_approvals.py` and
  `flake8` (per `.flake8` config; `make lint` in WSL). Both clean; black only joined
  over-wrapped lines in the new code (line-length 160).
- [x] **3.4** Update this plan's Status section to reflect completion; commit (repo
  convention: `[minor]`/`[patch]` prefix; end commit message with
  `Co-Authored-By: Claude Code <noreply@anthropic.com>`).

## Deliverables

- Reusable primitives in [`src/mas/devops/olm.py`](../../src/mas/devops/olm.py)
- Refactored `applySubscription` with opt-in approval interaction modes
- Comprehensive unit tests in `test/src/test_olm_approvals.py`
- No breaking changes for external consumers

## Out of Scope (handled in later phases)

- Namespace-scoped status aggregation and pause semantics → Phase 2
- Ordered approval plans, CLI tool, Slack integration → Phase 3
