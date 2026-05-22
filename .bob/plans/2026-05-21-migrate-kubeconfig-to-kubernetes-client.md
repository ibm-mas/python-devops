# Migrate from kubeconfig to Official Kubernetes Python Client

## Objective

Replace the unmaintained `kubeconfig` package with the official `kubernetes` Python client to ensure Python 3.12+ compatibility, active maintenance, and eliminate dependency on external kubectl binary.

## Critical Rules

- Maintain backward compatibility - function signatures must remain unchanged
- All existing tests must pass without modification
- Validate with `black` and `flake8` after each code change
- No functional changes - only replace the underlying implementation
- Update copyright headers to 2026 where files are modified

## Execution Plan

### Phase 1: Dependency Management

- [ ] **1.1** Remove `kubeconfig` from [`setup.py`](setup.py:57)
- [ ] **1.2** Validate: Run `python setup.py check` to ensure setup.py is valid

### Phase 2: Refactor `ocp.py`

- [ ] **2.1** Update imports in [`src/mas/devops/ocp.py`](src/mas/devops/ocp.py:14-15)
  - [ ] Replace `from kubeconfig import KubeConfig` with `from kubernetes import config`
  - [ ] Replace `from kubeconfig.exceptions import KubectlNotFoundError` with `from kubernetes.config.config_exception import ConfigException`
  - [ ] Add `import tempfile` and `import os` for temp file handling

- [ ] **2.2** Refactor [`connect()`](src/mas/devops/ocp.py:28) function
  - [ ] Create kubeconfig dict structure with cluster, user, and context
  - [ ] Write dict to temporary file using `tempfile.NamedTemporaryFile`
  - [ ] Load config using `config.load_kube_config(config_file=temp_kubeconfig)`
  - [ ] Clean up temporary file with `os.unlink()`
  - [ ] Update exception handling from `KubectlNotFoundError` to `ConfigException`
  - [ ] Update docstring to reflect new implementation (remove kubectl references)

- [ ] **2.3** Update copyright header to include 2026

- [ ] **2.4** Validate Phase 2
  - [ ] Run `wsl bash -lc "black src/mas/devops/ocp.py"`
  - [ ] Run `wsl bash -lc "flake8 src/mas/devops/ocp.py"`
  - [ ] Verify no syntax errors

### Phase 3: Refactor `tekton.py`

- [ ] **3.1** Update imports in [`src/mas/devops/tekton.py`](src/mas/devops/tekton.py:21)
  - [ ] Remove `from kubeconfig import kubectl`
  - [ ] Add `from kubernetes import client, utils`
  - [ ] Ensure `import yaml` is present

- [ ] **3.2** Refactor [`updateTektonDefinitions()`](src/mas/devops/tekton.py:333) function
  - [ ] Create `k8s_client = client.ApiClient()`
  - [ ] Read YAML file and parse with `yaml.safe_load_all()`
  - [ ] Iterate through YAML objects and apply with `utils.create_from_dict()`
  - [ ] Set namespace in metadata if not present
  - [ ] Add error handling for `FileNotFoundError`, `yaml.YAMLError`, and API exceptions
  - [ ] Update docstring to reflect new implementation and exceptions

- [ ] **3.3** Update copyright header to include 2026

- [ ] **3.4** Validate Phase 3
  - [ ] Run `wsl bash -lc "black src/mas/devops/tekton.py"`
  - [ ] Run `wsl bash -lc "flake8 src/mas/devops/tekton.py"`
  - [ ] Verify no syntax errors

### Phase 4: Testing

- [ ] **4.1** Create unit tests for `ocp.connect()` in `test/src/test_ocp_connect.py`
  - [ ] Test successful connection
  - [ ] Test connection with TLS skip
  - [ ] Test connection failure handling
  - [ ] Test ConfigException handling

- [ ] **4.2** Create unit tests for `tekton.updateTektonDefinitions()` in `test/src/test_tekton_update.py`
  - [ ] Test successful YAML application
  - [ ] Test FileNotFoundError handling
  - [ ] Test invalid YAML handling
  - [ ] Test multiple resources in single file

- [ ] **4.3** Validate Phase 4
  - [ ] Run `wsl bash -lc "pytest test/src/test_ocp_connect.py -v"`
  - [ ] Run `wsl bash -lc "pytest test/src/test_tekton_update.py -v"`
  - [ ] Verify all new tests pass

### Phase 5: Integration Testing

- [ ] **5.1** Run full existing test suite
  - [ ] Run `wsl bash -lc "pytest test/ -v"`
  - [ ] Verify all existing tests still pass
  - [ ] Document any test failures and root cause

- [ ] **5.2** Run code quality checks
  - [ ] Run `wsl bash -lc "black src/mas/devops/ocp.py src/mas/devops/tekton.py"`
  - [ ] Run `wsl bash -lc "flake8 src/mas/devops/ocp.py src/mas/devops/tekton.py"`
  - [ ] Verify no violations

- [ ] **5.3** Validate Phase 5
  - [ ] All tests pass
  - [ ] No flake8 violations
  - [ ] No black formatting issues

### Phase 6: Documentation

- [ ] **6.1** Review and update documentation files
  - [ ] Check [`README.md`](README.md:1) for kubeconfig references
  - [ ] Check [`CONTRIBUTING.md`](CONTRIBUTING.md:1) for setup instructions
  - [ ] Update if any references to kubeconfig exist

- [ ] **6.2** Validate Phase 6
  - [ ] Documentation is accurate and up-to-date
  - [ ] No broken references or outdated instructions

## Validation

### Success Criteria

1. **Dependency removed**: `kubeconfig` no longer in [`setup.py`](setup.py:57)
2. **Code quality**: All files pass `black` and `flake8` validation
3. **Tests pass**: All existing tests pass without modification
4. **New tests**: New unit tests for refactored functions pass
5. **Copyright updated**: Modified files have 2026 in copyright header
6. **Documentation**: No references to kubeconfig package remain

### Commands to Run

```bash
# Code formatting and linting
wsl bash -lc "black src/mas/devops/ocp.py src/mas/devops/tekton.py"
wsl bash -lc "flake8 src/mas/devops/ocp.py src/mas/devops/tekton.py"

# Run all tests
wsl bash -lc "pytest test/ -v"

# Verify setup.py
python setup.py check
```

### Expected Results

- Black: No files reformatted
- Flake8: No violations
- Pytest: All tests pass (exact count TBD based on existing test suite)
- Setup.py: No errors or warnings