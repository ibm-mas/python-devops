# Project Overview

## What This Project Is

`python-devops` is a Python library and CLI toolkit that supports the IBM Maximo Application Suite (MAS) DevOps ecosystem. It is consumed by the MAS CLI tool and provides:

1. **Common utility functions** — shared logic reused across MAS CLI operations (DB2 validation, Slack notifications, OCP/OLM helpers, user management, backup/restore, etc.)
2. **Catalog data** — version-controlled data about MAS application catalogs that drives application version management; this area changes most frequently
3. **Pipeline run definitions** — Jinja2-templated Tekton `PipelineRun` YAMLs that the CLI renders and submits to interact with Tekton pipelines on OpenShift

## Goals & Objectives

- Provide a stable, installable Python package (`pip install`) that the MAS CLI and related tooling can depend on
- Centralise DevOps automation logic (deployments, validations, notifications) so it isn't duplicated across scripts
- Keep catalog version data up to date so the CLI can resolve correct application versions at runtime
- Generate well-formed Tekton `PipelineRun` manifests from CLI commands

## Key Stakeholders / Users

- **IBM MAS engineers** — contributors who add features, fix bugs, and update catalog data (~20–30 active contributors)
- **Customers** — install and use the MAS CLI, which pulls this package as a dependency; they benefit from it indirectly

## Repository Structure

```
bin/                    # Thin CLI entry-point scripts (mas-devops-*)
src/mas/devops/
  data/                 # Catalog version data (changes most frequently)
  templates/            # Jinja2 PipelineRun / Tekton YAML templates
  aiservice.py          # AI service helpers
  backup.py / restore.py
  db2.py                # DB2 validation
  mas/                  # MAS-specific modules
  ocp.py                # OpenShift helpers
  olm.py                # OLM subscription helpers
  pre_install.py
  saas/                 # SaaS-specific modules
  slack.py              # Slack notifications
  sls.py                # SLS helpers
  tekton.py             # Tekton pipeline interaction
  users.py
  utils.py
test/src/mock/          # Unit tests (pytest)
tekton/src/             # Jinja2 source templates for Tekton tasks/pipelines
tekton/target/          # Generated Tekton YAML (not committed)
```

## Important Modules

| Module | Change Frequency | Notes |
|--------|-----------------|-------|
| `data/` (catalog data) | High | Version pins for MAS apps; updated on every release cycle |
| `templates/` (PipelineRun J2) | Medium | Updated per pipeline/feature changes |
| `tekton/src/` (Tekton task/pipeline templates) | Medium | Generated via `ansible-playbook`; see `tekton-development.md` |
| Python utilities (`db2`, `ocp`, `olm`, `slack`, etc.) | Low–Medium | Changes driven by roadmap/application needs |

## Integration Points

- **ansible-devops**: Ansible roles call these Python utilities for infrastructure setup
- **MAS CLI**: Primary consumer; installs this package and calls its entry points
- **OpenShift / Tekton**: Pipeline runs are submitted to an OCP cluster running Tekton
