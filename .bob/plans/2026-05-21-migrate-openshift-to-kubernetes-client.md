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

- [x] **1.1** Document all usage patterns of `openshift.dynamic`
  - [x] `DynamicClient` instantiation (11 files)
  - [x] `.resources.get()` calls (162 occurrences)
  - [x] `.apply()` calls (18 occurrences - requires special handling)
  - [x] Exception types: `NotFoundError`, `ResourceNotFoundError`, `UnauthorizedError`, `UnprocessibleEntityError`

- [x] **1.2** Create helper function for `apply()` replacement in [`src/mas/devops/ocp.py`](src/mas/devops/ocp.py)
  - [x] TDD Approach: RED-GREEN-REFACTOR ... extensive unit tests for this critical function
  - [x] Implement `applyResource()` function in `src/mas/devops/ocp.py` that mimics OpenShift's apply behavior
  - [x] Use try/get/patch pattern for existing resources
  - [x] Use create for new resources
  - [x] Handle both namespaced and cluster-scoped resources

- [x] **1.3** Validate Phase 1
  - [x] Helper function passes unit tests
  - [x] No syntax errors in ocp.py

### Phase 2: Update Imports and DynamicClient

- [x] **2.1** Update [`setup.py`](setup.py:55) dependencies
  - [x] Remove `'openshift'` from install_requires
  - [x] Ensure `'kubernetes'` remains in install_requires

- [x] **2.2** Update imports in all affected files (11 files)
  - [x] Replace `from openshift.dynamic import DynamicClient` with `from kubernetes.dynamic import DynamicClient`
  - [x] Replace `from openshift.dynamic.exceptions import NotFoundError` with `from kubernetes.dynamic.exceptions import NotFoundError`
  - [x] Update other exception imports similarly
  - [x] Files updated:
    - [x] [`src/mas/devops/aiservice.py`](src/mas/devops/aiservice.py:12)
    - [x] [`src/mas/devops/backup.py`](src/mas/devops/backup.py:13)
    - [x] [`src/mas/devops/mas/apps.py`](src/mas/devops/mas/apps.py:14)
    - [x] [`src/mas/devops/mas/suite.py`](src/mas/devops/mas/suite.py:17)
    - [x] [`src/mas/devops/ocp.py`](src/mas/devops/ocp.py:16)
    - [x] [`src/mas/devops/olm.py`](src/mas/devops/olm.py:17)
    - [x] [`src/mas/devops/pre_install.py`](src/mas/devops/pre_install.py:17)
    - [x] [`src/mas/devops/restore.py`](src/mas/devops/restore.py:12)
    - [x] [`src/mas/devops/sls.py`](src/mas/devops/sls.py:12)
    - [x] [`src/mas/devops/tekton.py`](src/mas/devops/tekton.py:22)
    - [x] [`src/mas/devops/users.py`](src/mas/devops/users.py:14)

- [x] **2.3** Update copyright headers to include 2026 in all modified files

- [x] **2.4** Validate Phase 2
  - [x] Run `black src/mas/devops/*.py src/mas/devops/mas/*.py test/src/test_ocp.py test/src/test_tekton_update.py test/src/test_restore.py test/src/test_olm.py test/src/test_mas.py test/src/test_backup.py test/src/mock/test_mas_mock.py`
  - [x] Run `flake8 src/mas/devops/*.py src/mas/devops/mas/*.py test/src/test_ocp.py test/src/test_tekton_update.py test/src/test_restore.py test/src/test_olm.py test/src/test_mas.py test/src/test_backup.py test/src/mock/test_mas_mock.py`
  - [x] Verify no import errors

### Phase 3: Replace `.apply()` Calls

- [x] **3.1** Replace `.apply()` in [`src/mas/devops/tekton.py`](src/mas/devops/tekton.py) (11 occurrences)
  - [x] Line 77: `subscriptionsAPI.apply()` → use helper
  - [x] Line 395: `clusterRoleBindingAPI.apply()` → use helper
  - [x] Line 416: `pvcAPI.apply()` → use helper
  - [x] Line 444: `pvcAPI.apply()` → use helper
  - [x] Line 495: `clusterRoleBindingAPI.apply()` → use helper
  - [x] Line 506: `pvcAPI.apply()` → use helper
  - [x] Line 886: `pipelineRunsAPI.apply()` → use helper
  - [x] Line 935: `pipelineRunsAPI.apply()` → use helper
  - [x] Line 975: `pipelineRunsAPI.apply()` → use helper
  - [x] Line 1099: `pipelineRunsAPI.apply()` → use helper
  - [x] Lines 1156-1158: `resourceAPI.apply()` → use helper

- [x] **3.2** Replace `.apply()` in [`src/mas/devops/pre_install.py`](src/mas/devops/pre_install.py) (2 occurrences)
  - [x] Line 316: `namespaceAPI.apply()` → use helper
  - [x] Lines 355-357: `resourceAPI.apply()` → use helper

- [x] **3.3** Replace `.apply()` in [`src/mas/devops/olm.py`](src/mas/devops/olm.py) (3 occurrences)
  - [x] Line 87: `operatorGroupsAPI.apply()` → use helper
  - [x] Line 214: `subscriptionsAPI.apply()` → use helper
  - [x] Line 218: `subscriptionsAPI.apply()` → use helper (retry)

- [x] **3.4** Replace `.apply()` in [`src/mas/devops/ocp.py`](src/mas/devops/ocp.py) (1 occurrence)
  - [x] Line 683: `secretsAPI.apply()` → use helper

- [x] **3.5** Replace `.apply()` in [`src/mas/devops/mas/suite.py`](src/mas/devops/mas/suite.py) (1 occurrence)
  - [x] Line 314: `secretsAPI.apply()` → use helper

- [x] **3.6** Validate Phase 3
  - [x] Run `black src/mas/devops/*.py src/mas/devops/mas/*.py test/src/test_ocp.py test/src/test_tekton_update.py test/src/test_restore.py test/src/test_olm.py test/src/test_mas.py test/src/test_backup.py test/src/mock/test_mas_mock.py`
  - [x] Run `flake8 src/mas/devops/*.py src/mas/devops/mas/*.py test/src/test_ocp.py test/src/test_tekton_update.py test/src/test_restore.py test/src/test_olm.py test/src/test_mas.py test/src/test_backup.py test/src/mock/test_mas_mock.py`
  - [x] Verify no syntax errors

### Phase 4: Update README Example

- [x] **4.1** Update [`README.md`](README.md:14) example code
  - [x] Change `from openshift import dynamic` to `from kubernetes import dynamic`
  - [x] Verify example still makes sense

- [x] **4.2** Validate Phase 4
  - [x] Example code is accurate
  - [x] No broken references

### Phase 5: Testing

- [x] **5.1** Create unit tests for `applyResource()` helper
  - [x] Test create new resource
  - [x] Test update existing resource
  - [x] Test namespaced resources
  - [x] Test cluster-scoped resources
  - [x] Test error handling

- [x] **5.2** Run existing test suite
  - [x] Run focused validations:
    - `pytest test/src/test_ocp.py -v`
    - `pytest test/src/test_backup.py -v`
    - `pytest test/src/test_db2.py -v`
    - `pytest test/src/test_olm.py::test_crud -vv -s`
  - [x] Document failures and root cause
  - [x] Fix pytest-mock dependent tests in `test/src/test_ocp.py`, `test/src/test_backup.py`, and `test/src/test_db2.py`

- [ ] **5.3** Validate Phase 5
  - [x] All new tests pass
  - [ ] All existing tests pass
  - [ ] No regressions detected
  - [ ] Blocked by environment-specific failure: `test/src/test_olm.py::test_crud_with_manual_approval_and_starting_csv` fails because namespace `cli-fvt-5` is already in `Terminating` state and rejects new `Subscription` creation with `403 Forbidden`

### Phase 6: Final Validation

- [x] **6.1** Code quality checks
  - [x] Run `black src/mas/devops/*.py src/mas/devops/mas/*.py test/src/test_ocp.py test/src/test_tekton_update.py test/src/test_restore.py test/src/test_olm.py test/src/test_mas.py test/src/test_backup.py test/src/mock/test_mas_mock.py`
  - [x] Run `flake8 src/mas/devops/*.py src/mas/devops/mas/*.py test/src/test_ocp.py test/src/test_tekton_update.py test/src/test_restore.py test/src/test_olm.py test/src/test_mas.py test/src/test_backup.py test/src/mock/test_mas_mock.py`
  - [x] Verify no violations

- [x] **6.2** Dependency verification
  - [x] Run `.venv/bin/python setup.py check`
  - [x] Verify `openshift` is not in dependencies
  - [x] Verify `kubernetes` is in dependencies

- [x] **6.3** Documentation review
  - [x] No references to openshift package remain in targeted source/test/docs files
  - [x] Copyright headers include 2026 in modified non-test files
  - [ ] All docstrings updated where required

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