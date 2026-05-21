# Migrate from openshift to Kubernetes Python Client

## Objective

Replace the `openshift` package with the official `kubernetes` Python client's `DynamicClient` to ensure better maintenance, broader community support, and eliminate dependency on the OpenShift-specific client library.

## Critical Rules

- Maintain backward compatibility - all function signatures must remain unchanged
- All existing tests must pass without modification
- The `apply()` method is OpenShift-specific and must be replaced with create/patch logic
- Validate with `black` and `flake8` after each code change
- Update copyright headers to 2026 where files are modified
- Test incrementally - validate each file after refactoring

## Execution Plan

### Phase 1: Analysis and Preparation

- [ ] **1.1** Document all usage patterns of `openshift.dynamic`
  - [ ] `DynamicClient` instantiation (11 files)
  - [ ] `.resources.get()` calls (162 occurrences)
  - [ ] `.apply()` calls (18 occurrences - requires special handling)
  - [ ] Exception types: `NotFoundError`, `ResourceNotFoundError`, `UnauthorizedError`, `UnprocessibleEntityError`

- [ ] **1.2** Create helper function for `apply()` replacement in [`src/mas/devops/ocp.py`](src/mas/devops/ocp.py)
  - [ ] Implement `applyResource()` function that mimics OpenShift's apply behavior
  - [ ] Use try/get/patch pattern for existing resources
  - [ ] Use create for new resources
  - [ ] Handle both namespaced and cluster-scoped resources

- [ ] **1.3** Validate Phase 1
  - [ ] Helper function passes unit tests
  - [ ] No syntax errors in ocp.py

### Phase 2: Update Imports and DynamicClient

- [ ] **2.1** Update [`setup.py`](setup.py:55) dependencies
  - [ ] Remove `'openshift'` from install_requires
  - [ ] Ensure `'kubernetes'` remains in install_requires

- [ ] **2.2** Update imports in all affected files (11 files)
  - [ ] Replace `from openshift.dynamic import DynamicClient` with `from kubernetes.dynamic import DynamicClient`
  - [ ] Replace `from openshift.dynamic.exceptions import NotFoundError` with `from kubernetes.dynamic.exceptions import NotFoundError`
  - [ ] Update other exception imports similarly
  - [ ] Files to update:
    - [ ] [`src/mas/devops/aiservice.py`](src/mas/devops/aiservice.py:12)
    - [ ] [`src/mas/devops/backup.py`](src/mas/devops/backup.py:13)
    - [ ] [`src/mas/devops/mas/apps.py`](src/mas/devops/mas/apps.py:14)
    - [ ] [`src/mas/devops/mas/suite.py`](src/mas/devops/mas/suite.py:17)
    - [ ] [`src/mas/devops/ocp.py`](src/mas/devops/ocp.py:16)
    - [ ] [`src/mas/devops/olm.py`](src/mas/devops/olm.py:17)
    - [ ] [`src/mas/devops/pre_install.py`](src/mas/devops/pre_install.py:17)
    - [ ] [`src/mas/devops/restore.py`](src/mas/devops/restore.py:12)
    - [ ] [`src/mas/devops/sls.py`](src/mas/devops/sls.py:12)
    - [ ] [`src/mas/devops/tekton.py`](src/mas/devops/tekton.py:22)
    - [ ] [`src/mas/devops/users.py`](src/mas/devops/users.py:14)

- [ ] **2.3** Update copyright headers to include 2026 in all modified files

- [ ] **2.4** Validate Phase 2
  - [ ] Run `wsl bash -lc "black src/mas/devops/*.py src/mas/devops/mas/*.py"`
  - [ ] Run `wsl bash -lc "flake8 src/mas/devops/*.py src/mas/devops/mas/*.py"`
  - [ ] Verify no import errors

### Phase 3: Replace `.apply()` Calls

- [ ] **3.1** Replace `.apply()` in [`src/mas/devops/tekton.py`](src/mas/devops/tekton.py) (11 occurrences)
  - [ ] Line 77: `subscriptionsAPI.apply()` → use helper
  - [ ] Line 395: `clusterRoleBindingAPI.apply()` → use helper
  - [ ] Line 416: `pvcAPI.apply()` → use helper
  - [ ] Line 444: `pvcAPI.apply()` → use helper
  - [ ] Line 495: `clusterRoleBindingAPI.apply()` → use helper
  - [ ] Line 506: `pvcAPI.apply()` → use helper
  - [ ] Line 886: `pipelineRunsAPI.apply()` → use helper
  - [ ] Line 935: `pipelineRunsAPI.apply()` → use helper
  - [ ] Line 975: `pipelineRunsAPI.apply()` → use helper
  - [ ] Line 1099: `pipelineRunsAPI.apply()` → use helper
  - [ ] Lines 1156-1158: `resourceAPI.apply()` → use helper

- [ ] **3.2** Replace `.apply()` in [`src/mas/devops/pre_install.py`](src/mas/devops/pre_install.py) (2 occurrences)
  - [ ] Line 316: `namespaceAPI.apply()` → use helper
  - [ ] Lines 355-357: `resourceAPI.apply()` → use helper

- [ ] **3.3** Replace `.apply()` in [`src/mas/devops/olm.py`](src/mas/devops/olm.py) (3 occurrences)
  - [ ] Line 87: `operatorGroupsAPI.apply()` → use helper
  - [ ] Line 214: `subscriptionsAPI.apply()` → use helper
  - [ ] Line 218: `subscriptionsAPI.apply()` → use helper (retry)

- [ ] **3.4** Replace `.apply()` in [`src/mas/devops/ocp.py`](src/mas/devops/ocp.py) (1 occurrence)
  - [ ] Line 683: `secretsAPI.apply()` → use helper

- [ ] **3.5** Replace `.apply()` in [`src/mas/devops/mas/suite.py`](src/mas/devops/mas/suite.py) (1 occurrence)
  - [ ] Line 314: `secretsAPI.apply()` → use helper

- [ ] **3.6** Validate Phase 3
  - [ ] Run `wsl bash -lc "black src/mas/devops/*.py src/mas/devops/mas/*.py"`
  - [ ] Run `wsl bash -lc "flake8 src/mas/devops/*.py src/mas/devops/mas/*.py"`
  - [ ] Verify no syntax errors

### Phase 4: Update README Example

- [ ] **4.1** Update [`README.md`](README.md:14) example code
  - [ ] Change `from openshift import dynamic` to `from kubernetes import dynamic`
  - [ ] Verify example still makes sense

- [ ] **4.2** Validate Phase 4
  - [ ] Example code is accurate
  - [ ] No broken references

### Phase 5: Testing

- [ ] **5.1** Create unit tests for `applyResource()` helper
  - [ ] Test create new resource
  - [ ] Test update existing resource
  - [ ] Test namespaced resources
  - [ ] Test cluster-scoped resources
  - [ ] Test error handling

- [ ] **5.2** Run existing test suite
  - [ ] Run `wsl bash -lc "pytest test/ -v"`
  - [ ] Document any failures and root cause
  - [ ] Fix any issues found

- [ ] **5.3** Validate Phase 5
  - [ ] All new tests pass
  - [ ] All existing tests pass
  - [ ] No regressions detected

### Phase 6: Final Validation

- [ ] **6.1** Code quality checks
  - [ ] Run `wsl bash -lc "black src/mas/devops/*.py src/mas/devops/mas/*.py"`
  - [ ] Run `wsl bash -lc "flake8 src/mas/devops/*.py src/mas/devops/mas/*.py"`
  - [ ] Verify no violations

- [ ] **6.2** Dependency verification
  - [ ] Run `python setup.py check`
  - [ ] Verify `openshift` is not in dependencies
  - [ ] Verify `kubernetes` is in dependencies

- [ ] **6.3** Documentation review
  - [ ] All docstrings updated
  - [ ] Copyright headers include 2026
  - [ ] No references to openshift package remain

## Implementation Details

### Helper Function: `applyResource()`

Add to [`src/mas/devops/ocp.py`](src/mas/devops/ocp.py):

```python
def applyResource(
    dynClient: DynamicClient,
    apiVersion: str,
    kind: str,
    body: dict,
    namespace: str = None
) -> dict:
    """
    Apply a resource (create or update) similar to kubectl apply.

    Mimics OpenShift's apply() behavior by attempting to get the resource first,
    then patching if it exists or creating if it doesn't.

    Parameters:
        dynClient (DynamicClient): Kubernetes Dynamic Client
        apiVersion (str): API version of the resource
        kind (str): Kind of the resource
        body (dict): Resource body to apply
        namespace (str, optional): Namespace for namespaced resources

    Returns:
        dict: The created or updated resource

    Raises:
        ApiException: If the operation fails
    """
    resourceAPI = dynClient.resources.get(api_version=apiVersion, kind=kind)
    name = body.get('metadata', {}).get('name')

    try:
        # Try to get existing resource
        if namespace:
            existing = resourceAPI.get(name=name, namespace=namespace)
        else:
            existing = resourceAPI.get(name=name)

        # Resource exists, patch it
        if namespace:
            return resourceAPI.patch(
                body=body,
                name=name,
                namespace=namespace,
                content_type='application/merge-patch+json'
            )
        else:
            return resourceAPI.patch(
                body=body,
                name=name,
                content_type='application/merge-patch+json'
            )
    except NotFoundError:
        # Resource doesn't exist, create it
        if namespace:
            return resourceAPI.create(body=body, namespace=namespace)
        else:
            return resourceAPI.create(body=body)
```

### Usage Pattern

Replace:
```python
resourceAPI.apply(body=resource, namespace=namespace)
```

With:
```python
from mas.devops.ocp import applyResource
applyResource(
    dynClient,
    resource['apiVersion'],
    resource['kind'],
    resource,
    namespace
)
```

## Validation

### Success Criteria

1. **Dependency removed**: `openshift` no longer in [`setup.py`](setup.py:55)
2. **Imports updated**: All 11 files use `kubernetes.dynamic` instead of `openshift.dynamic`
3. **Apply replaced**: All 18 `.apply()` calls replaced with helper function
4. **Code quality**: All files pass `black` and `flake8` validation
5. **Tests pass**: All existing tests pass without modification
6. **Copyright updated**: Modified files have 2026 in copyright header

### Commands to Run

```bash
# Code formatting and linting
wsl bash -lc "black src/mas/devops/*.py src/mas/devops/mas/*.py"
wsl bash -lc "flake8 src/mas/devops/*.py src/mas/devops/mas/*.py"

# Run all tests
wsl bash -lc "pytest test/ -v"

# Verify setup.py
python setup.py check
```

### Expected Results

- Black: No files reformatted
- Flake8: No violations
- Pytest: All tests pass
- Setup.py: No errors, `openshift` not in dependencies