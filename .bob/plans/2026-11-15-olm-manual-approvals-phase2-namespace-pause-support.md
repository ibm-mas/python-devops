# OLM Manual Approval Support — Phase 2: Namespace Awareness & Pause Support

> Part 2 of 3. Related plans:
> [Phase 1 — Core Approval Primitives](2026-11-15-olm-manual-approvals-phase1-core-primitives.md)
> [Phase 3 — Guided Approval Workflow](2026-11-15-olm-manual-approvals-phase3-guided-approval-workflow.md)

## Objective

Provide the namespace-scoped primitives the wider automation needs to **note that a specific
namespace has manual approvals required and effectively pause its normal processing until the
approval is given**. This is the foundation layer that ansible-devops playbooks and tekton
pipelines will call at the top of each processing step.

Builds directly on the Phase 1 primitives (`getPendingInstallPlans`, `approveInstallPlan`,
`waitForInstallPlanComplete`, `waitForSubscriptionStable`).

## Background

- The wider automation (install/update/upgrade pipelines) currently assumes subscriptions roll
  forward automatically (`AtLatestKnown`). With Manual approval, upgraded namespaces sit in
  `UpgradePending` with InstallPlans in `RequiresApproval`, and downstream waits
  (e.g. `waitForAppReady`, CSV checks) would block or misreport.
- There is no single-call way today to ask "does this namespace need attention?" — a caller
  would have to list subscriptions, read each `spec.installPlanApproval`, then list
  InstallPlans and filter by phase.
- Notification infrastructure already exists: [`src/mas/devops/slack.py`](../../src/mas/devops/slack.py)
  and the `mas-devops-notify-slack` entry point; recent work routes pipeline/task failure
  notifications to a channel as well as the Majel thread.

## Critical Rules

- Namespace status functions must be **non-blocking** and cheap (a small, bounded number of API
  round-trips) — they will be called frequently as gate checks in pipelines.
- The blocking variant must accept a timeout and an optional `onPending` callback; no
  unbounded waits in new code.
- The pending-approval result shape is a contract: Phase 3 (CLI, Slack messages, approval
  plans) and the external pipeline repos will consume it — document it precisely and treat
  changes to it as breaking.
- Backward compatibility with all existing functions.
- Validate with `black` and `flake8`; update copyright headers; follow
  `.bob/rules/python/docstrings.md`.

## Open Decisions (to be made before/during implementation)

- [ ] **Pause semantics — the central decision of this phase.** A human approval can take
  hours; Tekton PipelineRuns have `activeDeadlineSeconds`, so "sleep until approved" inside a
  run is fragile. Two models:
  - **Return-and-resume** (recommended primary): automation detects the pending approval,
    emits a notification containing everything needed to decide, and exits cleanly; the
    pipeline is re-run/resumed after approval and re-enters idempotently (all `apply*`
    functions already are idempotent).
    - *Consequence:* the pipeline repos need a small re-entry convention (a "nothing to do
      until approval X" clean exit vs a failure), and the resume path must tolerate the
      approval having happened out-of-band.
  - **Block-with-timeout**: automation waits in-process for the approval, suitable for
    short windows (attended/interactive rollouts) but not for overnight unattended runs.
  - Phase 2 should deliver **both** and let callers choose, but the default and the
  documentation emphasis need deciding. Recommendation: return-and-resume as the documented
  default contract.
- [ ] **Result shape for `getNamespaceApprovalStatus`** — draft:
  ```python
  {
      "namespace": "mas-inst1-manage",
      "manualSubscriptions": ["ibm-mas-manage"],        # subscriptions with Manual mode
      "pendingApprovals": [                              # InstallPlans in RequiresApproval
          {
              "installPlan": "install-plan-abc",
              "subscription": "ibm-mas-manage",
              "package": "ibm-mas-manage",
              "csvNames": ["ibm-manage.v9.1.0"],
              "currentCSV": "ibm-manage.v9.0.x",        # from subscription status.installedCSV
              "targetCSV": "ibm-manage.v9.1.0",
              "created": "2026-11-15T10:00:00Z",
          }
      ],
      "blocking": True,   # any pending approval that gates further processing
  }
  ```
  Decide: plain dict (recommended, Jinja2/JSON friendly) vs dataclass; whether `blocking`
  should be a derived helper or a field.
- [ ] **`onPending` callback contract** for `waitForNamespaceApprovals`: invoked once when an
  approval first appears, or on every poll? Receives the full status dict? Can it abort the
  wait (returning False)?
- [ ] **Exit semantics for return-and-resume**: does the library define a distinguishable
  result/exception for "paused awaiting approval" (so a pipeline can exit 0 with a marker),
  and if so what does it look like? This borders on pipeline-repo territory — decide how much
  convention this repo should own.
- [ ] **Scope of "namespace"**: MAS app namespaces (`mas-{id}-{appId}`), core
  (`mas-{id}-core`), aiservice (`aiservice-{id}`), plus non-MAS operators (SLS, Mongo, etc.)
  all live in different namespaces. Confirm `getNamespaceApprovalStatus` stays strictly
  namespace-scoped (caller iterates namespaces) vs an optional instance-level rollup
  helper `getInstanceApprovalStatus(dynClient, instanceId)` that knows the namespace layout.
  The instance-level rollup overlaps with Phase 3's `buildApprovalPlan` — decide where it
  lives.
- [ ] **Slack integration depth in this phase**: is `onPending` + callers composing their own
  Slack messages enough for Phase 2, or should a ready-made "approval required" message
  formatter live here (moving some of Phase 3 forward)?

## Execution Plan

### Phase 1: Non-blocking status

- [ ] **1.1** `getNamespaceApprovalStatus(dynClient, namespace) -> dict`
  - Single round-trip per resource type (list subscriptions in namespace, list InstallPlans
    in namespace); join in memory.
  - Subscriptions with `spec.installPlanApproval == "Manual"` → `manualSubscriptions`.
  - InstallPlans in `RequiresApproval` → `pendingApprovals` (enriched as per Phase 1
    `getPendingInstallPlans`, plus `currentCSV` from the owning subscription's
    `status.installedCSV`).
  - `blocking` = any pending approval exists.
- [ ] **1.2** Optional instance-level rollup (pending the scope decision above):
  `getInstanceApprovalStatus(dynClient, instanceId)` iterating
  `mas-{id}-core`, `mas-{id}-{appId}` for installed apps (reuse
  [getAppsSubscriptionChannel](../../src/mas/devops/mas/apps.py#L200)-style detection),
  and `aiservice-{id}`.
- [ ] **1.3** Helper `isApprovalRequired(dynClient, namespace) -> bool` — the cheapest
  possible gate check for automation that only wants a yes/no.

### Phase 2: Blocking wait + callback

- [ ] **2.1** `waitForNamespaceApprovals(dynClient, namespace, timeout=None, pollInterval=30, onPending=None) -> dict`
  - Polls `getNamespaceApprovalStatus` until `blocking` is False, or timeout expiry
    (a `None`/generous default timeout is acceptable here only because the function is
    explicitly the blocking variant — document the tradeoff).
  - `onPending` fires per the contract decided above — hook point for Slack notification.
  - Returns the final status dict.
- [ ] **2.2** Wire `applySubscription`'s `onApprovalRequired="return"` mode (Phase 1 task
  2.2) to produce the same result shape as `getNamespaceApprovalStatus.pendingApprovals`
  entries, so callers see one consistent contract from both entry points.

### Phase 3: Integration enablers for the wider automation

- [ ] **3.1** Document the adoption pattern for pipeline/playbook authors (docs update in
  [docs/index.md](../../docs/index.md) or a dedicated doc):
  - gate check at step start: `isApprovalRequired` / `getNamespaceApprovalStatus`
  - return-and-resume: notify + clean exit; re-run resumes idempotently
  - block-with-timeout: `waitForNamespaceApprovals` with `onPending` notification
- [ ] **3.2** Verify interplay with existing waits: `waitForAppReady`
  ([apps.py:120](../../src/mas/devops/mas/apps.py#L120)) and similar must not be reached in a
  state where the operator itself is awaiting approval — confirm the gate check placement
  guidance covers this (wait-for-approval *before* wait-for-ready).

### Phase 4: Tests

- [ ] **4.1** `test/src/test_olm_namespace_approvals.py` (or extend the Phase 1 test file,
  per the naming decision):
  - status: empty namespace; Manual subscription with no pending plan; pending plan
    enrichment (ownerReferences vs label resolution); `blocking` derivation.
  - gate: `isApprovalRequired` true/false cases.
  - wait: returns when approval resolved out-of-band (mock phase transition); timeout
    expiry; `onPending` invocation contract.
  - instance rollup (if in scope): core + apps + aiservice namespaces.
- [ ] **4.2** `make test` green; existing tests unmodified.

## Deliverables

- `getNamespaceApprovalStatus` / `isApprovalRequired` / `waitForNamespaceApprovals` (+
  optional instance rollup) in [`src/mas/devops/olm.py`](../../src/mas/devops/olm.py)
  (or the module location decided in Phase 1).
- A documented, stable pending-approval result contract shared with `applySubscription`.
- Documented adoption pattern for the pipeline/playbook repos.

## Out of Scope (handled in later phases)

- Standalone approve/list CLI and ordered rollout plans → Phase 3
- Changes in the external pipeline/ansible repos themselves (they consume this library;
  their own repos track that work)
