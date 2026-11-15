# OLM Manual Approval Support — Phase 3: Guided Approval Workflow

> Part 3 of 3. Related plans:
> [Phase 1 — Core Approval Primitives](2026-11-15-olm-manual-approvals-phase1-core-primitives.md)
> [Phase 2 — Namespace Awareness & Pause Support](2026-11-15-olm-manual-approvals-phase2-namespace-pause-support.md)

## Objective

Deliver the guided approval experience: functions that **approve the manual approvals in
dependency order** and an interface that walks the user through them — e.g. a pipeline that
recommends "approve namespace 1 subscription update", waits for it to complete, then
"approve namespace 2 update", and so on, for the rollout of an update.

This phase provides the ordering knowledge, the step-execution mechanics, the CLI, and the
notification formatting. The pipeline repos (tekton) provide only thin condition-checks
between stages; the sequencing and approval mechanics live here.

Builds on Phase 1 (approve/wait primitives) and Phase 2 (namespace status contract).

## Background

- MAS rollout dependency order is already known to this repo:
  - core first: `mas-{id}-core` (package `ibm-mas`)
  - then applications: `mas-{id}-{appId}` (packages `ibm-mas-{appId}`) — the app list is in
    [APP_IDS in mas/apps.py](../../src/mas/devops/mas/apps.py)
  - then AI Service: `aiservice-{id}` (package `ibm-aiservice`)
  - supporting operators (SLS, MongoDb, etc.) may also hold pending approvals in their own
    namespaces.
- Notification routing exists: [`src/mas/devops/slack.py`](../../src/mas/devops/slack.py),
  `mas-devops-notify-slack` entry point; recent work posts pipeline/task failures to both a
  channel and the Majel thread.
- CLI conventions: thin wrapper scripts in `bin/mas-devops-*` listed in
  [`setup.py`](../../setup.py) `scripts`, importing implementation from
  `src/mas/devops/` (see AGENTS.md "When Adding New CLI Tool").

## Critical Rules

- The ordering is a **recommendation**, not enforcement: approving out of order must not be
  blocked by this library (the operator/OLM behavior governs what actually succeeds); the
  plan builder only sorts and annotates.
- Each executed step must be independently verifiable: approve → wait for InstallPlan
  `Complete` → verify the subscription settles (`waitForSubscriptionStable`) before
  declaring the step done.
- All step operations idempotent and re-runnable — a guided session may be interrupted and
  restarted at any point (aligns with the return-and-resume model from Phase 2).
- No secrets or cluster identifiers in Slack message templates beyond what existing
  notifications already carry — follow the existing slack.py message conventions.
- Validate with `black` and `flake8`; update copyright headers; follow
  `.bob/rules/python/docstrings.md`.
- New CLI tool requires: implementation module, `bin/` script, `setup.py` scripts entry,
  tests mirroring module structure, README/docs mention.

## Open Decisions (to be made before/during implementation)

- [ ] **Ordering source**: hardcode core → apps → aiservice in this repo (it already owns
  `APP_IDS`) vs derive dynamically from cluster state (CSV dependencies) vs accept an
  explicit order from the caller with a sensible default. Recommendation: sensible default
  derived from `APP_IDS` + caller override.
- [ ] **Where the plan builder lives**: new module `src/mas/devops/approvals.py` vs
  extension of `mas/suite.py` / `olm.py`. Recommendation: new `approvals.py` — it cuts
  across olm + mas concerns and both `olm.py` and `suite.py` are already large.
- [ ] **`ApprovalPlan` representation**: list of dicts reusing the Phase 2
  `pendingApprovals` entry shape plus ordering metadata (index, dependsOn) vs a dataclass.
  Must stay JSON-serializable if the CLI and pipelines pass it around. Recommendation:
  dicts.
- [ ] **CLI tool name and subcommand surface** — draft `mas-devops-olm-approvals`:
  - `list [--namespace X]` — show pending approvals
  - `approve --namespace X [--package P | --install-plan N]` — approve one
  - `wait --namespace X [--timeout T]` — wait for completion
  - `plan --instance-id I` — show the ordered rollout plan
  - `step --instance-id I [--index N]` — approve-and-wait the next (or Nth) step
  - Decide whether `step` belongs in the CLI or only as a library function used by
  pipelines (a human running `step` repeatedly is the "guided interface"; a pipeline
  calling `executeApprovalStep` in a loop with notifications is the automated variant).
- [ ] **Slack interaction model**: notification-only (message says "run
  `mas-devops-olm-approvals approve ...` to approve") vs interactive (buttons/action
  handlers that call back into something that runs the approve). Interactive requires
  infrastructure outside this repo (a listener); recommendation for this phase:
  **notification-only**, designing the message format so an interactive backend can be
  added later (Phase 4 / future).
- [ ] **What "step complete" means for gating the next step**: InstallPlan `Complete`
  alone, or also the new CSV reaching its readiness state (e.g. deployment available)?
  OLM InstallPlan Complete does not guarantee the operator is running. Decide the default
  and whether it is configurable.
- [ ] **Partial-failure handling in `executeApprovalStep`**: InstallPlan `Failed`, or
  subscription never settling after approval — raise, return a failure status in the plan,
  or both (status field + optional strict mode)?
- [ ] **Whether the CLI needs a `--dry-run`** on `approve`/`step` (recommendation: yes,
  trivial to add, useful for rehearsal).

## Execution Plan

### Phase 1: Plan builder

- [ ] **1.1** Create `src/mas/devops/approvals.py` (per module-location decision).
- [ ] **1.2** `buildApprovalPlan(dynClient, instanceId, order=None) -> dict`
  - Collect pending approvals across the instance's namespaces (core, installed apps via
    subscription detection, aiservice, optionally supporting operator namespaces).
  - Sort into the recommended dependency order; caller-supplied `order` (list of
    appId/namespace identifiers) overrides.
  - Each step: namespace, package, subscription name, InstallPlan name, currentCSV →
    targetCSV, plus ordering metadata.
  - Steps also carry a stable step identifier so interrupted sessions can resume by
    reference.
- [ ] **1.3** `describeApprovalStep(step) -> str`
  - Human-readable line for CLI output and Slack messages, e.g.
    `Approve subscription update for ibm-manage in mas-inst1-manage (v9.0.x → v9.1.x)`.

### Phase 2: Step execution

- [ ] **2.1** `executeApprovalStep(dynClient, step, timeout=...) -> dict`
  - `approveInstallPlan` → `waitForInstallPlanComplete` → `waitForSubscriptionStable`
    (all Phase 1 primitives).
  - Returns the step result (approved/complete/skipped-already-complete/failed) plus the
    refreshed plan.
  - Handles out-of-band approval gracefully (step already approved by someone else →
    verify and continue).
- [ ] **2.2** `executeApprovalPlan(dynClient, instanceId, onStepComplete=None, ...)` —
  optional convenience to drive the whole sequence with a callback between steps
  (the automated variant of the guided interface). Default behavior between steps per the
  "step complete" decision.

### Phase 3: CLI tool

- [ ] **3.1** Implementation functions wired for CLI use (argparse, meaningful error
  messages, exit codes per AGENTS.md error-handling convention).
- [ ] **3.2** `bin/mas-devops-olm-approvals` thin wrapper script.
- [ ] **3.3** Register in [`setup.py`](../../setup.py) `scripts` list.
- [ ] **3.4** `--help` output verified after `make install` (per AGENTS.md).

### Phase 4: Slack notification formatting

- [ ] **4.1** Message formatter for "approval required" (single step) and "next step in
  plan" (guided sequence), including the CLI command to approve — built on
  [`slack.py`](../../src/mas/devops/slack.py) conventions and the Phase 2 status contract.
- [ ] **4.2** Hook point so pipelines can post these via the existing notify path
  (channel + Majel thread routing, per the recent notification work).

### Phase 5: Tests & docs

- [ ] **5.1** `test/src/test_approvals.py`:
  - plan builder: ordering (core → apps → aiservice), caller override, empty plan when
    nothing pending, resume identifier stability.
  - step execution: full approve → complete → stable path; already-approved no-op;
    InstallPlan Failed; timeout; out-of-band approval.
  - describe: message content.
- [ ] **5.2** CLI tests where practical (argument parsing, error paths) following existing
  bin test conventions.
- [ ] **5.3** Docs: new tool mention in [docs/index.md](../../docs/index.md) and the
  AGENTS.md "Common CLI Tools" reference.

## Deliverables

- `src/mas/devops/approvals.py`: `buildApprovalPlan`, `describeApprovalStep`,
  `executeApprovalStep`, `executeApprovalPlan`
- `bin/mas-devops-olm-approvals` CLI (list / approve / wait / plan / step) registered in
  setup.py
- Slack message formatters for approval-required and next-step notifications
- Tests and docs

## Out of Scope / Future (Phase 4 candidates)

- Interactive Slack approval (buttons + listener backend) — the message format designed here
  should make this a drop-in later
- Web/visual interface for the guided rollout
- Automatic sequencing *inside* pipelines (pipeline repos adopt the library; their work is
  tracked in their own repos)
