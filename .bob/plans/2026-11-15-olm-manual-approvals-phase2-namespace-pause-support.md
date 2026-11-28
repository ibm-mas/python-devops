# OLM Manual Approval Support — Phase 2: Namespace Awareness & Pause Support

> Part 2 of 3. Related plans:
> [Phase 1 — Core Approval Primitives](2026-11-15-olm-manual-approvals-phase1-core-primitives.md)
> [Phase 3 — Guided Approval Workflow](2026-11-15-olm-manual-approvals-phase3-guided-approval-workflow.md)

## Status (updated 2026-11-20 — COMPLETE, pending commit)

**Phase 2 is finished on branch `manualsubs`: all three namespace functions implemented in
[`src/mas/devops/olm.py`](../../src/mas/devops/olm.py), 14 new tests in
[test_olm_approvals.py](../../test/src/test_olm_approvals.py), adoption-pattern docs in
[docs/api/olm.md](../../docs/api/olm.md).**

- 52/52 pass in test_olm_approvals.py + test_olm_installplan_selection.py; full unit suite
  449 passed / 4 skipped (only pre-existing environmental `test_slack.py` failures).
- `black` and `flake8` clean.
- Task 2.2 needed no code change: Phase 1's `_describePendingInstallPlan` already produces
  the shared contract; verified by
  `test_pending_approvals_share_the_apply_subscription_release_contract`.

Next step: commit, then Phase 3
([guided approval workflow](2026-11-15-olm-manual-approvals-phase3-guided-approval-workflow.md)).

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

## Decisions (resolved 2026-11-20)

- [x] **Pause semantics**: deliver **both** patterns and document them **equally — there is no
  default**. This repo is the underlying function layer; whether callers use return-and-resume
  or block-with-timeout is entirely up to them.
- [x] **Result shape for `getNamespaceApprovalStatus`**: plain dict (Jinja2/JSON friendly),
  `blocking` as a derived field, per the draft below with one change: a **mixed-mode namespace
  is reported, not raised** — `approvalMode` is `"Mixed"` when subscriptions disagree. Real
  MAS namespaces legitimately contain mixes (OLM auto-creates dependency subscriptions with
  default Automatic mode — see the Phase 1 discovery), and a gate check must not raise on the
  state it exists to detect. Callers wanting the strict single-mode accessor still have
  Phase 1's `getSubscriptionApprovalMode` (which raises on a mix).
- [x] **`onPending` callback contract** for `waitForNamespaceApprovals`: invoked on **every
  poll** while approvals are pending; receives the **full status dict** and a **poll counter**
  (1-based); returning **False aborts the wait**, with the current (still blocking) status
  returned to the caller.
- [x] **Exit semantics for return-and-resume**: the library defines **no** distinguishable
  paused-state result or exception. `waitForNamespaceApprovals`'s return only tells the caller
  whether the approvals were done or not (via `blocking`); how to handle each situation is the
  caller's decision. Timeout expiry still raises `OLMTimeoutError`, per the Phase 1 wait
  contract.
- [x] **Scope of "namespace"**: strictly 1:1 with a namespace — **no rollup logic** (the
  instance-level helper in task 1.2 is dropped). Callers iterate namespaces themselves.
- [x] **Slack integration depth**: `onPending` is all this repo provides. Whether and how to
  notify is the caller's decision; no message formatter here.

Draft result shape (contract — treat changes as breaking):

```python
{
    "namespace": "mas-inst1-manage",
    # "Manual" | "Automatic" | "Mixed" | None (no subscriptions). Unset spec
    # counts as Automatic; a mix is reported as "Mixed", never raised here.
    "approvalMode": "Manual",
    "pendingApprovals": [                              # InstallPlans in RequiresApproval
        {
            "installPlan": "install-plan-abc",
            "namespace": "mas-inst1-manage",
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

## Execution Plan

### Phase 1: Non-blocking status — COMPLETE

- [x] **1.1** `getNamespaceApprovalStatus(dynClient, namespace) -> dict`
  - Single round-trip per resource type (list subscriptions in namespace, list InstallPlans
    in namespace); join in memory.
  - Namespace approval mode computed from the subscription list already fetched:
    `approvalMode` is the shared mode, `"Mixed"` on disagreement, `None` for an empty
    namespace (per the decision above — no raising here).
  - InstallPlans in `RequiresApproval` → `pendingApprovals` (enriched via Phase 1's
    `_describePendingInstallPlan`, which already matches this contract — see task 2.2).
  - `blocking` = any pending approval exists.
- [x] **1.2** ~~Optional instance-level rollup~~ — **dropped** per the scope decision:
  strictly namespace-scoped, callers iterate.
- [x] **1.3** Helper `isApprovalRequired(dynClient, namespace) -> bool` — the cheapest
  possible gate check for automation that only wants a yes/no (single InstallPlan list).

### Phase 2: Blocking wait + callback — COMPLETE

- [x] **2.1** `waitForNamespaceApprovals(dynClient, namespace, timeout=None, pollInterval=30, onPending=None) -> dict`
  - Polls `getNamespaceApprovalStatus` until `blocking` is False, or timeout expiry
    (a `None` default timeout is acceptable here only because the function is
    explicitly the blocking variant — document the tradeoff).
  - `onPending(status, pollCount)` fires on **every poll** while approvals are pending
    (1-based counter); returning `False` aborts the wait and returns the current status.
  - Timeout expiry raises `OLMTimeoutError`; there is no special paused-state result —
    the returned status's `blocking` field tells the caller whether the approvals were
    done (per the decisions above).
  - Returns the final status dict.
- [x] **2.2** Wire `applySubscription`'s `onApprovalRequired="return"` mode (Phase 1 task
  2.2) to produce the same result shape as `getNamespaceApprovalStatus.pendingApprovals`
  entries, so callers see one consistent contract from both entry points.
  Already satisfied by Phase 1: `_describePendingInstallPlan` produces exactly this shape
  (a superset including `namespace`) for both `getPendingInstallPlans` and the
  `applySubscription` release path. Verified by an assertion in the tests, no code change
  (`test_pending_approvals_share_the_apply_subscription_release_contract`).

### Phase 3: Integration enablers for the wider automation — COMPLETE

- [x] **3.1** Document the adoption pattern for pipeline/playbook authors (prose section in
  [docs/api/olm.md](../../docs/api/olm.md), which mkdocstrings renders alongside the API
  reference):
  - gate check at step start: `isApprovalRequired` / `getNamespaceApprovalStatus`
  - return-and-resume: detect, notify, exit; re-run resumes idempotently
  - block-with-timeout: `waitForNamespaceApprovals` with `onPending` notification
  - Both patterns documented **equally, no default** — the choice is the caller's
- [x] **3.2** Verify interplay with existing waits: `waitForAppReady`
  ([apps.py:120](../../src/mas/devops/mas/apps.py#L120)) and similar must not be reached in a
  state where the operator itself is awaiting approval — confirm the gate check placement
  guidance covers this (wait-for-approval *before* wait-for-ready).
  Covered by the note in docs/api/olm.md (`waitForAppReady` confirmed present at
  apps.py:120).

### Phase 4: Tests — COMPLETE

- [x] **4.1** Extend [test_olm_approvals.py](../../test/src/test_olm_approvals.py) (decision:
  one mock harness per feature area, no cross-test-file imports) with namespace-status tests:
  - status: empty namespace; Manual subscription with no pending plan; pending plan
    enrichment (ownerReferences vs label resolution); `blocking` derivation; mixed-mode
    namespace reported as `"Mixed"` (not raised).
  - gate: `isApprovalRequired` true/false cases.
  - wait: returns when approval resolved out-of-band (mock phase transition); timeout
    expiry; `onPending` invoked every poll with status + poll counter; `onPending`
    returning False aborts and returns the still-blocking status.
  - shape: `getNamespaceApprovalStatus.pendingApprovals` entries match the
    `applySubscription` release-path approval info (task 2.2 verification).
- [x] **4.2** `make test` green; existing tests unmodified. Result: 449 passed / 4 skipped,
  only the pre-existing environmental `test_slack.py` failures (`SLACK_TOKEN is not set`).

## Deliverables

- `getNamespaceApprovalStatus` / `isApprovalRequired` / `waitForNamespaceApprovals` in
  [`src/mas/devops/olm.py`](../../src/mas/devops/olm.py).
- A documented, stable pending-approval result contract shared with `applySubscription`.
- Documented adoption pattern for the pipeline/playbook repos.

## Out of Scope (handled in later phases)

- Standalone approve/list CLI and ordered rollout plans → Phase 3
- Instance-level (multi-namespace) status rollup → callers iterate; Phase 3's
  `buildApprovalPlan` territory if wanted at all
- Changes in the external pipeline/ansible repos themselves (they consume this library;
  their own repos track that work)
