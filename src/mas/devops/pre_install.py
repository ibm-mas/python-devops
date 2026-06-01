# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

import logging
import yaml

from os import path, listdir

from kubernetes import client as k8s_client
from openshift.dynamic import DynamicClient
from jinja2 import Environment

logger = logging.getLogger(__name__)

DEFAULT_PREINSTALL_MAS_RBAC_ROOT = "/opt/app-root/rbac"


def _validate_selected_apps(selectedApps: list[str] | None) -> set[str]:
    if not selectedApps:
        return set()

    validApps = {
        "core",
        "aiservice",
        "arcgis",
        "facilities",
        "iot",
        "manage",
        "monitor",
        "optimizer",
        "predict",
        "visualinspection"
    }

    validatedApps = set()
    for app in selectedApps:
        if app not in validApps:
            raise ValueError(f"Unsupported selected app: {app}")
        validatedApps.add(app)

    return validatedApps


def _get_selected_operator_dirs(selectedApps: set[str]) -> set[str]:

    appToOperatorDir = {
        "core": "ibm-mas",
        "aiservice": "ibm-aiservice",
        "arcgis": "ibm-mas-arcgis",
        "facilities": "ibm-mas-facilities",
        "iot": "ibm-mas-iot",
        "manage": "ibm-mas-manage",
        "monitor": "ibm-mas-monitor",
        "optimizer": "ibm-mas-optimizer",
        "predict": "ibm-mas-predict",
        "visualinspection": "ibm-mas-visualinspection"
    }

    return {appToOperatorDir[app] for app in selectedApps}


def _should_apply_preinstall_mas_rbac_file(fileName: str, adminMode: str) -> bool:
    lowerName = path.basename(fileName).lower()

    if lowerName == "kustomization.yaml":
        return False

    if not (lowerName.endswith(".yml") or lowerName.endswith(".yaml")):
        return False

    if adminMode == "cluster":
        return lowerName.startswith("cluster-role-")

    if adminMode == "namespaced":
        return lowerName.startswith("role-non-essential-")

    return False


def _collect_preinstall_mas_rbac_files_from_source(
    sourceOperatorsRoot: str,
    masVersion: str,
    adminMode: str,
    operatorNames: set[str] | None = None
) -> list[str]:
    if not path.isdir(sourceOperatorsRoot):
        logger.debug(f"Skipping missing RBAC source root {sourceOperatorsRoot}")
        return []

    if operatorNames is None:
        operatorNames = {
            operatorName for operatorName in listdir(sourceOperatorsRoot)
            if path.isdir(path.join(sourceOperatorsRoot, operatorName))
        }

    manifestFiles = []
    for operatorName in sorted(operatorNames):
        operatorRoot = path.join(sourceOperatorsRoot, operatorName)
        if not path.isdir(operatorRoot):
            logger.debug(f"Skipping missing operator root {operatorRoot}")
            continue

        versionDir = path.join(operatorRoot, "rbac", masVersion)
        if not path.isdir(versionDir):
            logger.debug(f"Skipping missing RBAC version directory {versionDir}")
            continue

        for manifestName in sorted(listdir(versionDir)):
            manifestFile = path.join(versionDir, manifestName)
            if not path.isfile(manifestFile):
                continue

            if _should_apply_preinstall_mas_rbac_file(manifestName, adminMode):
                manifestFiles.append(manifestFile)

    return manifestFiles


def _discover_preinstall_mas_rbac_files(
    rbacRootDir: str | None,
    masVersion: str,
    adminMode: str,
    selectedApps: set[str]
) -> list[str]:
    if not rbacRootDir:
        rbacRootDir = DEFAULT_PREINSTALL_MAS_RBAC_ROOT

    selectedOperatorDirs = _get_selected_operator_dirs(selectedApps)

    sourceRoots = [
        (
            path.join(rbacRootDir, "maximo-operator-catalog", "operators"),
            selectedOperatorDirs
        ),
        (
            path.join(rbacRootDir, "openshift-platform", "operators"),
            None
        )
    ]

    manifestFiles = []
    for sourceRoot, operatorNames in sourceRoots:
        manifestFiles.extend(
            _collect_preinstall_mas_rbac_files_from_source(
                sourceOperatorsRoot=sourceRoot,
                masVersion=masVersion,
                adminMode=adminMode,
                operatorNames=operatorNames
            )
        )

    return list(dict.fromkeys(manifestFiles))


def _get_preinstall_mas_rbac_namespaces(masInstanceId: str, adminMode: str, selectedApps: set[str]) -> set[str]:

    if adminMode == "cluster":
        return set()

    namespaces = {f"mas-{masInstanceId}-core"}

    appNamespaces = {
        "aiservice": f"aiservice-{masInstanceId}",
        "arcgis": f"mas-{masInstanceId}-arcgis",
        "facilities": f"mas-{masInstanceId}-facilities",
        "iot": f"mas-{masInstanceId}-iot",
        "manage": f"mas-{masInstanceId}-manage",
        "monitor": f"mas-{masInstanceId}-monitor",
        "optimizer": f"mas-{masInstanceId}-optimizer",
        "predict": f"mas-{masInstanceId}-predict",
        "visualinspection": f"mas-{masInstanceId}-visualinspection"
    }

    for app in selectedApps:
        if app in appNamespaces:
            namespaces.add(appNamespaces[app])

    return namespaces


def _check_self_subject_access(
    dynClient: DynamicClient,
    verb: str,
    resource: str,
    group: str = "rbac.authorization.k8s.io",
    namespace: str | None = None
) -> bool:
    authAPI = k8s_client.AuthorizationV1Api(dynClient.client)
    review = k8s_client.V1SelfSubjectAccessReview(
        spec=k8s_client.V1SelfSubjectAccessReviewSpec(
            resource_attributes=k8s_client.V1ResourceAttributes(
                namespace=namespace,
                verb=verb,
                resource=resource,
                group=group
            )
        )
    )
    result = authAPI.create_self_subject_access_review(body=review)
    status = getattr(result, "status", None)
    return bool(getattr(status, "allowed", False))


def buildClusterAdminPermissionMatrix() -> list[dict[str, str]]:
    return [
        {"verb": "create", "resource": "namespaces", "group": ""},
        {"verb": "create", "resource": "clusterroles"},
        {"verb": "update", "resource": "clusterroles"},
        {"verb": "create", "resource": "clusterrolebindings"},
        {"verb": "update", "resource": "clusterrolebindings"},
    ]


def requiresPreInstallRBAC(
    dynClient: DynamicClient,
    targetVersion: str,
    permissionMode: str | None = None,
    skipPreinstallRbac: bool = False
) -> bool:
    """
    Determine if pre-install RBAC is required and can be applied for the target version.

    This function is used across install, update, and upgrade operations to determine
    if RBAC resources are required and should be applied before launching the pipeline.
    It will raise an exception if permissions are missing and RBAC is required.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        targetVersion (str): Target MAS version (e.g., "9.2.0", "9.2.x", "9.2.0-pre.stable").
        permissionMode (str | None): Permission mode ("cluster", "namespaced", "minimal").
                                     If "minimal", RBAC is skipped.
        skipPreinstallRbac (bool): If True, skip RBAC application (for install --skip-preinstall-rbac).

    Returns:
        bool: True if RBAC should be applied, False if it should be skipped.

    Raises:
        PermissionError: If user lacks required permissions and RBAC is needed.
    """
    from .utils import isVersionEqualOrAfter

    # Extract base version for comparison
    baseVersion = targetVersion.split("-")[0].replace(".x", ".0") if targetVersion else ""

    # Only apply for MAS >= 9.2.0
    if not baseVersion or not isVersionEqualOrAfter("9.2.0", baseVersion):
        logger.info(f"Target version {targetVersion} is < 9.2.0, skipping pre-install RBAC")
        return False

    # Skip for minimal mode - operator will apply essential roles
    if permissionMode == "minimal":
        logger.info("Minimal permission mode detected, skipping pre-install RBAC")
        return False

    # Skip if explicitly requested (install --skip-preinstall-rbac)
    if skipPreinstallRbac:
        logger.info("Skipping pre-install RBAC as requested by --skip-preinstall-rbac flag")
        return False

    # Check if user has cluster-admin permissions
    permissionResults = permissionCheckForRBAC(dynClient)
    hasPreInstallRBACAccess = all(result["allowed"] for result in permissionResults)

    if hasPreInstallRBACAccess:
        logger.info(f"User has required permissions for pre-install RBAC (target version: {targetVersion})")
        return True

    # No permissions - this is a blocking error
    errorMsg = (
        f"Current user does not have cluster-admin permissions required to apply pre-install RBAC for MAS {targetVersion}. "
        f"Permission mode '{permissionMode or 'cluster'}' requires the following permissions:\n"
    )
    for result in permissionResults:
        if not result["allowed"]:
            errorMsg += f"  - {result['verb']} {result['resource']} (group: {result.get('group', 'core')})\n"

    errorMsg += "\nPlease contact your OpenShift cluster administrator to apply the required RBAC, or use --skip-preinstall-rbac if RBAC was already applied."

    raise PermissionError(errorMsg)


def permissionCheckForRBAC(
    dynClient: DynamicClient,
    checks: list[dict[str, str]] | None = None
) -> list[dict[str, str | bool]]:
    if checks is None:
        checks = buildClusterAdminPermissionMatrix()

    results = []

    for check in checks:
        verb = check["verb"]
        resource = check["resource"]
        group = check.get("group", "rbac.authorization.k8s.io")
        namespace = check.get("namespace")

        allowed = _check_self_subject_access(
            dynClient=dynClient,
            verb=verb,
            resource=resource,
            group=group,
            namespace=namespace
        )

        result: dict[str, str | bool] = {
            "verb": verb,
            "resource": resource,
            "group": group,
            "allowed": allowed
        }

        if namespace is not None:
            result["namespace"] = namespace

        results.append(result)

    return results


def applyPreInstallMASRBAC(
    dynClient: DynamicClient,
    masVersion: str,
    masInstanceId: str,
    adminMode: str,
    selectedApps: list[str] | None = None,
    rbacRootDir: str | None = None
) -> None:
    if not rbacRootDir:
        rbacRootDir = DEFAULT_PREINSTALL_MAS_RBAC_ROOT

    # Minimal mode - essential roles will be applied by each operator
    if adminMode == "minimal":
        logger.info("Minimal admin mode - essential roles will be applied by each operator")
        return

    # For cluster mode, use ibm-mas operator only (apps not required)
    if adminMode == "cluster":
        validatedApps = {"core"}  # Use core which maps to ibm-mas operator
        logger.info("Cluster admin mode - using ibm-mas operator only")
    else:
        # For namespaced mode, validate and use selected apps
        validatedApps = _validate_selected_apps(selectedApps)
        if not validatedApps:
            logger.info("No selected apps provided for namespaced mode pre-install MAS RBAC apply")
            return

    manifestFiles = _discover_preinstall_mas_rbac_files(
        rbacRootDir=rbacRootDir,
        masVersion=masVersion,
        adminMode=adminMode,
        selectedApps=validatedApps
    )

    logger.info(
        f"Applying pre-install MAS RBAC from {rbacRootDir} for MAS {masVersion}, "
        f"masInstanceId={masInstanceId}, adminMode={adminMode}, "
        f"selectedApps={sorted(validatedApps)}, "
        f"manifestCount={len(manifestFiles)}"
    )

    if not manifestFiles:
        logger.info("No pre-install MAS RBAC manifests selected for apply")
        return

    namespaceAPI = dynClient.resources.get(api_version="v1", kind="Namespace")
    requiredNamespaces = _get_preinstall_mas_rbac_namespaces(
        masInstanceId=masInstanceId,
        adminMode=adminMode,
        selectedApps=validatedApps
    )

    for namespace in sorted(requiredNamespaces):
        logger.info(f"Ensuring namespace exists for pre-install MAS RBAC: {namespace}")
        namespaceAPI.apply(body={
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": namespace
            }
        })

    env = Environment()
    appliedResourceCount = 0

    for manifestFile in manifestFiles:
        logger.info(f"Applying pre-install MAS RBAC manifest {manifestFile}")
        with open(manifestFile, "r") as file:
            template = env.from_string(file.read())
            renderedManifest = template.render(mas_instance_id=masInstanceId)

        for resourceBody in yaml.safe_load_all(renderedManifest):
            if resourceBody is None:
                continue

            apiVersion = resourceBody["apiVersion"]
            kind = resourceBody["kind"]
            metadata = resourceBody["metadata"]
            resourceName = metadata["name"]
            resourceNamespace = metadata.get("namespace")

            if kind in {"Role", "RoleBinding"} and not resourceNamespace:
                raise ValueError(
                    f"Namespaced RBAC resource {kind}/{resourceName} from {manifestFile} is missing metadata.namespace"
                )

            logger.debug(
                f"Applying {kind} {resourceName} "
                f"(apiVersion={apiVersion}, namespace={resourceNamespace})"
            )

            resourceAPI = dynClient.resources.get(api_version=apiVersion, kind=kind)
            if resourceNamespace:
                resourceAPI.apply(body=resourceBody, namespace=resourceNamespace)
            else:
                resourceAPI.apply(body=resourceBody)

            appliedResourceCount += 1

    logger.info(
        f"Pre-install MAS RBAC apply completed: processedFiles={len(manifestFiles)}, "
        f"appliedResources={appliedResourceCount}"
    )
