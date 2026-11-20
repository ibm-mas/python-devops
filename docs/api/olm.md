# OLM Module

The `olm` module provides functions for managing Operator Lifecycle Manager (OLM) operations.

## Manual approval workflows

Operators installed with `installPlanApproval: "Manual"` generate InstallPlans that sit in
`RequiresApproval` until a human approves them. The namespace-level functions let automation
detect and handle that state. There is no prescribed usage pattern — both models below are
equally supported and the choice belongs to the caller.

### Gate check

At the start of each processing step, check whether the namespace needs attention:

```python
from mas.devops.olm import getNamespaceApprovalStatus, isApprovalRequired

if isApprovalRequired(dynClient, "mas-inst1-manage"):
    status = getNamespaceApprovalStatus(dynClient, "mas-inst1-manage")
    for approval in status["pendingApprovals"]:
        print(f"{approval['package']} is waiting to move to {approval['targetCSV']}")
```

`isApprovalRequired` is the cheapest yes/no check (a single InstallPlan list).
`getNamespaceApprovalStatus` returns the full status dict:

| Key | Value |
| --- | --- |
| `namespace` | The namespace inspected |
| `approvalMode` | `"Manual"`, `"Automatic"`, `"Mixed"` or `None` (no subscriptions) |
| `pendingApprovals` | Approval info dicts, one per InstallPlan in `RequiresApproval` |
| `blocking` | `True` when any InstallPlan is awaiting approval |

A namespace whose subscriptions mix approval modes is reported with `approvalMode: "Mixed"`
rather than raised — OLM auto-creates dependency subscriptions that can legitimately
introduce a mix. For waiting semantics a Mixed namespace behaves the same as Manual:
InstallPlans in `RequiresApproval` gate processing regardless of which subscription
generated them. `getSubscriptionApprovalMode` reports the same `"Mixed"` value for a
mixed namespace (with a warning logged).

### Return-and-resume

Detect the pending approval, emit whatever notification the caller wants, and exit cleanly.
Re-running after the approval is given resumes idempotently: all `apply*` functions are
idempotent and tolerate the approval having happened out-of-band.
`applySubscription` supports this directly — `onApprovalRequired="return"` (or a callable
returning `False`) makes it return a `(subscription, approvalInfo)` tuple instead of waiting
when an approval is outstanding.

### Block-with-timeout

For short windows (for example an attended rollout), wait in-process:

```python
from mas.devops.olm import waitForNamespaceApprovals

def notify(status, pollCount):
    # caller-owned notification, e.g. Slack; return False to abort the wait
    ...

status = waitForNamespaceApprovals(dynClient, "mas-inst1-manage", timeout=3600, onPending=notify)
if status["blocking"]:
    # the wait was aborted by notify returning False
    ...
```

`onPending(status, pollCount)` is invoked on every poll while approvals are pending, with
the full status dict and the 1-based poll number — this is the hook point for caller-owned
notifications. Timeout expiry raises `OLMTimeoutError`. There is no special result or
exception for "still awaiting approval": the `blocking` field of the returned status tells
the caller whether the approvals were completed, and handling each situation is the caller's
decision.

!!! note
    Place the approval gate check **before** readiness waits such as `waitForAppReady`: an
    operator whose upgrade is awaiting approval will never become ready, so
    wait-for-approval first, then wait-for-ready.

## API Reference

::: mas.devops.olm
