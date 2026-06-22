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
import re
import yaml
import base64

from datetime import datetime
from os import path

from time import sleep

from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import (
    NotFoundError,
    UnprocessibleEntityError,
    ApiException,
)

from jinja2 import Environment, FileSystemLoader

from .ocp import (
    getConsoleURL,
    waitForCRD,
    waitForDeployment,
    crdExists,
    waitForPVC,
    getStorageClasses,
    getStorageClassVolumeBindingMode,
    getClusterVersion,
)

logger = logging.getLogger(__name__)


def installOpenShiftPipelines(dynClient: DynamicClient, customStorageClassName: str = None) -> bool:
    """
    Install the OpenShift Pipelines Operator and wait for it to be ready to use.

    Creates the operator subscription, waits for the CRD and webhook to be ready,
    and handles PVC storage class configuration if needed.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        customStorageClassName (str, optional): Custom storage class name for Tekton PVC. Defaults to None.

    Returns:
        bool: True if installation is successful, False otherwise

    Raises:
        NotFoundError: If the package manifest is not found
        UnprocessibleEntityError: If the subscription cannot be created
    """
    packagemanifestAPI = dynClient.resources.get(api_version="packages.operators.coreos.com/v1", kind="PackageManifest")
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")

    # Create the Operator Subscription
    if not crdExists(dynClient, "pipelines.tekton.dev"):
        # Retry logic for finding the package manifest
        max_retries = 50
        retry_delay = 20  # seconds
        attempts = 0
        manifest = None

        logger.info("Attempting to locate OpenShift Pipelines Operator package manifest...")

        while attempts < max_retries:
            try:
                manifest = packagemanifestAPI.get(
                    name="openshift-pipelines-operator-rh",
                    namespace="openshift-marketplace",
                )
                logger.info("Successfully found OpenShift Pipelines Operator package manifest")
                break
            except NotFoundError as e:
                attempts += 1
                if attempts < max_retries:
                    logger.warning(f"Package manifest not found (attempt {attempts}/{max_retries}). Retrying in {retry_delay} seconds...")
                    sleep(retry_delay)
                else:
                    logger.error(f"Failed to find package manifest for Red Hat OpenShift Pipelines Operator after {max_retries} attempts")
                    logger.error(f"The operator package manifest is not available in the openshift-marketplace namespace: {e}")
                    return False
            except Exception as e:
                logger.error(f"Unexpected error while retrieving package manifest: {e}")
                return False

        if manifest is None:
            logger.error("Failed to retrieve package manifest - cannot proceed with operator installation")
            return False

        # Extract operator details from manifest
        try:
            defaultChannel = manifest.status.defaultChannel
            catalogSource = manifest.status.catalogSource
            catalogSourceNamespace = manifest.status.catalogSourceNamespace

            logger.info(f"OpenShift Pipelines Operator Details: {catalogSourceNamespace}/{catalogSource}@{defaultChannel}")

            # Create subscription
            templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
            env = Environment(loader=FileSystemLoader(searchpath=templateDir))
            template = env.get_template("subscription.yml.j2")
            renderedTemplate = template.render(
                subscription_name="openshift-pipelines-operator",
                subscription_namespace="openshift-operators",
                package_name="openshift-pipelines-operator-rh",
                package_channel=defaultChannel,
                catalog_name=catalogSource,
                catalog_namespace=catalogSourceNamespace,
            )
            subscription = yaml.safe_load(renderedTemplate)
            subscriptionsAPI.apply(body=subscription, namespace="openshift-operators")
            logger.info("OpenShift Pipelines Operator subscription created successfully")

        except UnprocessibleEntityError as e:
            logger.error(f"Error: Couldn't create/update OpenShift Pipelines Operator Subscription: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while creating operator subscription: {e}")
            return False

    # Wait for the CRD to be available
    logger.debug("Waiting for tasks.tekton.dev CRD to be available")
    foundReadyCRD = waitForCRD(dynClient, "tasks.tekton.dev")
    if foundReadyCRD:
        logger.info("OpenShift Pipelines Operator is installed and ready")
    else:
        logger.error("OpenShift Pipelines Operator is NOT installed and ready")
        return False

    # Wait for the webhook to be ready
    logger.debug("Waiting for tekton-pipelines-webhook Deployment to be ready")
    foundReadyWebhook = waitForDeployment(
        dynClient,
        namespace="openshift-pipelines",
        deploymentName="tekton-pipelines-webhook",
    )
    if foundReadyWebhook:
        logger.info("OpenShift Pipelines Webhook is installed and ready")
    else:
        logger.error("OpenShift Pipelines Webhook is NOT installed and ready")
        return False

    # Workaround for bug in OpenShift Pipelines/Tekton
    # -------------------------------------------------------------------------
    # Wait for the postgredb-tekton-results-postgres-0 PVC to be ready
    # this PVC doesn't come up when there's no default storage class is in the cluster,
    # this is causing the pvc to be in pending state and causing the tekton-results-postgres statefulSet in pending,
    # due to these resources not coming up, the MAS pre-install check in the pipeline times out checking the health of this statefulSet,
    # causing failure in pipeline.
    # Refer https://github.com/ibm-mas/cli/issues/1511
    logger.debug("Checking postgredb-tekton-results-postgres-0 PVC status")

    pvcAPI = dynClient.resources.get(api_version="v1", kind="PersistentVolumeClaim")
    pvcName = "postgredb-tekton-results-postgres-0"
    pvcNamespace = "openshift-pipelines"

    # Wait briefly for PVC to be created (max 5 minutes)
    maxInitialRetries = 60
    pvc = None
    for retry in range(maxInitialRetries):
        try:
            pvc = pvcAPI.get(name=pvcName, namespace=pvcNamespace)
            break
        except NotFoundError:
            if retry < maxInitialRetries - 1:
                logger.debug(f"Waiting 5s for PVC {pvcName} to be created (attempt {retry + 1}/{maxInitialRetries})...")
                sleep(5)

    if pvc is None:
        logger.error(f"PVC {pvcName} was not created after {maxInitialRetries * 5} seconds (5 minutes)")
        return False

    # Check if PVC is already bound
    if pvc.status.phase == "Bound":
        logger.info("OpenShift Pipelines postgres PVC is already bound and ready")
        return True

    # Check if PVC is pending without a storage class - needs immediate patching
    if pvc.status.phase == "Pending" and pvc.spec.storageClassName is None:
        logger.info("PVC is pending without storage class, attempting to patch immediately...")
        tektonPVCisReady = addMissingStorageClassToTektonPVC(
            dynClient=dynClient,
            namespace=pvcNamespace,
            pvcName=pvcName,
            storageClassName=customStorageClassName,
        )
        if tektonPVCisReady:
            logger.info("OpenShift Pipelines postgres is installed and ready")
            return True
        else:
            logger.error("OpenShift Pipelines postgres PVC is NOT ready after patching")
            return False

    # PVC exists with storage class but not bound yet - wait for it to bind
    logger.debug(f"PVC has storage class '{pvc.spec.storageClassName}', waiting for it to be bound...")
    foundReadyPVC = waitForPVC(dynClient, namespace=pvcNamespace, pvcName=pvcName)
    if foundReadyPVC:
        logger.info("OpenShift Pipelines postgres is installed and ready")
        return True
    else:
        logger.error("OpenShift Pipelines postgres PVC is NOT ready")
        return False


def enablePipelinesConsolePlugin(dynClient: DynamicClient) -> bool:
    """
    Enable the OpenShift Pipelines console plugin for OCP 4.21+.

    In OpenShift 4.21 and later, the Pipelines console plugin must be manually
    enabled by patching the Console operator configuration. This function:
    1. Detects the OCP version
    2. Checks if version >= 4.21
    3. Enables the plugin if not already enabled

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client

    Returns:
        bool: True if plugin is enabled or already enabled, False on error
    """
    try:
        # Get cluster version
        clusterVersion = getClusterVersion(dynClient)
        if not clusterVersion:
            logger.warning("Unable to determine cluster version, skipping plugin enablement")
            return True  # Non-fatal, return True to continue

        logger.debug(f"Detected OpenShift version: {clusterVersion}")

        # Parse version (e.g., "4.21.0" -> major=4, minor=21)
        versionParts = clusterVersion.split(".")
        if len(versionParts) < 2:
            logger.warning(f"Unable to parse cluster version '{clusterVersion}', skipping plugin enablement")
            return True

        try:
            majorVersion = int(versionParts[0])
            minorVersion = int(versionParts[1])
        except ValueError:
            logger.warning(f"Unable to parse version numbers from '{clusterVersion}', skipping plugin enablement")
            return True

        # Check if version requires plugin enablement (4.21+)
        requiresPlugin = (majorVersion == 4 and minorVersion >= 21) or (majorVersion > 4)

        if not requiresPlugin:
            logger.info(f"OpenShift version {clusterVersion} does not require manual plugin enablement")
            return True

        logger.info(f"OpenShift version {clusterVersion} requires Pipelines console plugin to be enabled")

        # Get Console Operator
        consoleAPI = dynClient.resources.get(api_version="operator.openshift.io/v1", kind="Console")
        console = consoleAPI.get(name="cluster")

        # Check if plugin is already enabled
        currentPlugins = console.spec.plugins if hasattr(console.spec, "plugins") and console.spec.plugins else []
        pluginName = "pipelines-console-plugin"

        if pluginName in currentPlugins:
            logger.info("Pipelines console plugin is already enabled")
            return True

        # Enable the plugin by patching the Console operator
        logger.info("Enabling Pipelines console plugin...")

        # Create patch to add plugin to the list
        updatedPlugins = list(currentPlugins) + [pluginName]
        patch = {"spec": {"plugins": updatedPlugins}}

        consoleAPI.patch(name="cluster", body=patch, content_type="application/merge-patch+json")

        logger.info("Successfully enabled Pipelines console plugin")
        return True

    except NotFoundError as e:
        logger.warning(f"Console operator not found: {e}")
        return True  # Non-fatal, plugin can be enabled manually
    except Exception as e:
        logger.error(f"Error enabling Pipelines console plugin: {e}")
        return False


def addMissingStorageClassToTektonPVC(dynClient: DynamicClient, namespace: str, pvcName: str, storageClassName: str = None) -> bool:
    """
    OpenShift Pipelines has a problem when there is no default storage class defined in a cluster, this function
    patches the PVC used to store pipeline results to add a specific storage class into the PVC spec and waits for the
    PVC to be bound.

    :param dynClient: Kubernetes client, required to work with PVC
    :type dynClient: DynamicClient
    :param namespace: Namespace where OpenShift Pipelines is installed
    :type namespace: str
    :param pvcName: Name of the PVC that we want to fix
    :type pvcName: str
    :param storageClassName: Name of the storage class that we want to update the PVC to reference (optional, will auto-select if not provided)
    :type storageClassName: str
    :return: True if PVC is successfully patched and bound, False otherwise
    :rtype: bool
    """
    pvcAPI = dynClient.resources.get(api_version="v1", kind="PersistentVolumeClaim")
    storageClassAPI = dynClient.resources.get(api_version="storage.k8s.io/v1", kind="StorageClass")

    try:
        pvc = pvcAPI.get(name=pvcName, namespace=namespace)

        # Check if PVC is pending and has no storage class
        if pvc.status.phase == "Pending" and pvc.spec.storageClassName is None:
            # Determine which storage class to use
            targetStorageClass = None

            if storageClassName is not None:
                # Verify the provided storage class exists
                try:
                    storageClassAPI.get(name=storageClassName)
                    targetStorageClass = storageClassName
                    logger.info(f"Using provided storage class '{storageClassName}' for PVC {pvcName}")
                except NotFoundError:
                    logger.warning(f"Provided storage class '{storageClassName}' not found, will try to detect available storage class")

            # If no valid custom storage class, try to detect one
            if targetStorageClass is None:
                logger.warning("No storage class provided or provided storage class not found, attempting to use first available storage class")
                storageClasses = getStorageClasses(dynClient)
                if len(storageClasses) > 0:
                    # Use the first available storage class
                    targetStorageClass = storageClasses[0].metadata.name
                    logger.info(f"Using first available storage class '{targetStorageClass}' for PVC {pvcName}")
                else:
                    logger.error(f"Unable to set storageClassName in PVC {pvcName}. No storage classes available in the cluster.")
                    return False

            # Patch the PVC with the storage class
            pvc.spec.storageClassName = targetStorageClass
            logger.info(f"Patching PVC {pvcName} with storageClassName: {targetStorageClass}")
            pvcAPI.patch(body=pvc, namespace=namespace)

            # Wait for the PVC to be bound
            maxRetries = 60
            foundReadyPVC = False
            retries = 0
            while not foundReadyPVC and retries < maxRetries:
                retries += 1
                try:
                    patchedPVC = pvcAPI.get(name=pvcName, namespace=namespace)
                    if patchedPVC.status.phase == "Bound":
                        foundReadyPVC = True
                        logger.info(f"PVC {pvcName} is now bound")
                    else:
                        logger.debug(f"Waiting 5s for PVC {pvcName} to be bound before checking again ...")
                        sleep(5)
                except NotFoundError:
                    logger.error(f"The patched PVC {pvcName} does not exist.")
                    return False

            return foundReadyPVC
        else:
            logger.warning(f"PVC {pvcName} is not in Pending state or already has a storageClassName")
            return pvc.status.phase == "Bound"

    except NotFoundError:
        logger.error(f"PVC {pvcName} does not exist")
        return False


def updateTektonDefinitions(dynClient: DynamicClient, namespace: str, yamlFile: str) -> None:
    """
    Install or update MAS Tekton pipeline and task definitions from a YAML file.

    Parses a YAML file containing multiple Tekton resources (pipelines, tasks, etc.)
    and applies each resource individually using the kubernetes python client.
    Includes retry logic to handle intermittent network failures common in OCP clusters.

    This is an all-or-nothing operation - if any resource fails to apply after retries,
    the function will raise an exception immediately without processing remaining resources.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to apply the definitions to
        yamlFile (str): Path to the YAML file containing Tekton definitions

    Returns:
        None

    Raises:
        FileNotFoundError: If the YAML file does not exist
        ApiException: If resource application fails after all retries or if API resource cannot be retrieved
    """
    if not path.isfile(yamlFile):
        logger.error(f"Tekton definitions file not found: {yamlFile}")
        raise FileNotFoundError(f"Tekton definitions file not found: {yamlFile}")

    # Load all resources from the YAML file
    with open(yamlFile, "r") as file:
        resources = list(yaml.safe_load_all(file))

    logger.info(f"Applying {len(resources)} Tekton resources from {yamlFile} to namespace {namespace}")

    # Retry configuration optimized for poor network conditions
    maxRetries = 10
    baseDelay = 1  # seconds
    maxDelay = 15  # seconds

    appliedCount = 0
    apiCache = {}  # Cache API objects by (apiVersion, kind) to avoid repeated discovery

    for resourceIndex, resourceBody in enumerate(resources, start=1):
        if resourceBody is None:
            continue

        apiVersion = resourceBody.get("apiVersion")
        kind = resourceBody.get("kind")
        metadata = resourceBody.get("metadata", {})
        name = metadata.get("name", "<unnamed>")

        logger.debug(f"Processing resource {resourceIndex}/{len(resources)}: {kind}/{name}")

        # Get or create cached API object
        apiKey = (apiVersion, kind)
        if apiKey not in apiCache:
            try:
                apiCache[apiKey] = dynClient.resources.get(api_version=apiVersion, kind=kind)
            except Exception as e:
                logger.error(f"Failed to get API resource for {kind} (apiVersion={apiVersion}): {e}")
                raise ApiException(f"Cannot proceed: Failed to get API resource for {kind} (apiVersion={apiVersion})")

        resourceAPI = apiCache[apiKey]

        # Apply resource with retry logic for transient failures
        for attempt in range(maxRetries):
            try:
                resourceAPI.apply(body=resourceBody, namespace=namespace)

                # Log success only if there were previous failures
                if attempt > 0:
                    logger.info(f"Successfully applied {kind}/{name} after {attempt + 1} attempts")
                else:
                    logger.debug(f"Applied {kind}/{name}")

                appliedCount += 1
                break  # Success, exit retry loop

            except ApiException as e:
                # Check if it's a retryable error
                errorMessage = str(e).lower()
                isRetryable = (
                    e.status in [429, 503, 504]
                    or "tls handshake timeout" in errorMessage
                    or "eof" in errorMessage
                    or "connection refused" in errorMessage
                    or "connection reset" in errorMessage
                    or "too many requests" in errorMessage
                    or "apiserver is shutting down" in errorMessage
                    or "net/http" in errorMessage
                )

                if isRetryable and attempt < maxRetries - 1:
                    # Exponential backoff with jitter
                    import random

                    waitTime = min(baseDelay * (2**attempt), maxDelay)
                    jitter = random.uniform(0, 0.1 * waitTime)
                    totalWait = waitTime + jitter

                    logger.warning(
                        f"Transient error applying {kind}/{name} " f"(attempt {attempt + 1}/{maxRetries}): {str(e)[:150]}. " f"Retrying in {totalWait:.1f}s..."
                    )
                    sleep(totalWait)
                else:
                    # Exhausted retries or non-retryable error - fail immediately
                    if isRetryable:
                        logger.error(f"Failed to apply {kind}/{name} after {maxRetries} attempts. " f"Last error: {e.status} - {str(e)[:200]}")
                    else:
                        logger.error(f"Failed to apply {kind}/{name}: {e.status} - {str(e)[:200]}")
                    raise ApiException(f"Failed to apply Tekton resource {kind}/{name} after {appliedCount} successful applications")

            except Exception as e:
                # Catch any other unexpected errors - fail immediately
                logger.error(f"Unexpected error applying {kind}/{name}: {type(e).__name__} - {str(e)[:200]}")
                raise

    # All resources applied successfully
    logger.info(f"Successfully applied all {appliedCount} Tekton resources")


def preparePipelinesNamespace(
    dynClient: DynamicClient,
    instanceId: str = None,
    storageClass: str = None,
    accessMode: str = None,
    waitForBind: bool = True,
    configureRBAC: bool = True,
    createConfigPVC: bool = True,
    createBackupPVC: bool = False,
    backupStorageSize: str = "20Gi",
):
    """
    Prepare a namespace for MAS pipelines by creating RBAC and PVC resources.

    Creates cluster-wide or instance-specific pipeline namespace with necessary
    role bindings and persistent volume claims.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        instanceId (str, optional): MAS instance ID. If None, creates cluster-wide namespace. Defaults to None.
        storageClass (str, optional): Storage class for the PVC. Defaults to None.
        accessMode (str, optional): Access mode for the PVC. Defaults to None.
        waitForBind (bool, optional): Whether to wait for PVC to bind. Defaults to True.
        configureRBAC (bool, optional): Whether to configure RBAC. Defaults to True.
        createConfigPVC (bool, optional): Whether to create config PVC. Defaults to True.
        createBackupPVC (bool, optional): Whether to create backup PVC. Defaults to False.
        backupStorageSize (str, optional): Size of the backup PVC storage. Defaults to "20Gi".

    Returns:
        None

    Raises:
        NotFoundError: If resources cannot be created
    """
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(loader=FileSystemLoader(searchpath=templateDir))
    if instanceId is None:
        namespace = "mas-pipelines"
        template = env.get_template("pipelines-rbac-cluster.yml.j2")
    else:
        namespace = f"mas-{instanceId}-pipelines"
        template = env.get_template("pipelines-rbac.yml.j2")

    if configureRBAC:
        # Create RBAC
        renderedTemplate = template.render(mas_instance_id=instanceId)
        logger.debug(renderedTemplate)
        crb = yaml.safe_load(renderedTemplate)
        clusterRoleBindingAPI = dynClient.resources.get(api_version="rbac.authorization.k8s.io/v1", kind="ClusterRoleBinding")
        clusterRoleBindingAPI.apply(body=crb, namespace=namespace)

    # Create PVC (instanceId namespace only)
    if instanceId is not None:
        pvcAPI = dynClient.resources.get(api_version="v1", kind="PersistentVolumeClaim")

        # Automatically determine if we should wait for PVC binding based on storage class
        volumeBindingMode = getStorageClassVolumeBindingMode(dynClient, storageClass)
        waitForBind = volumeBindingMode == "Immediate"

        # Create config PVC if requested
        if createConfigPVC:
            logger.info("Creating config PVC")
            template = env.get_template("pipelines-pvc.yml.j2")
            renderedTemplate = template.render(
                mas_instance_id=instanceId,
                pipeline_storage_class=storageClass,
                pipeline_storage_accessmode=accessMode,
            )
            logger.debug(renderedTemplate)
            pvc = yaml.safe_load(renderedTemplate)
            pvcAPI.apply(body=pvc, namespace=namespace)

            if waitForBind:
                logger.info(f"Storage class {storageClass} uses volumeBindingMode={volumeBindingMode}, waiting for config PVC to bind")
                pvcIsBound = False
                while not pvcIsBound:
                    configPVC = pvcAPI.get(name="config-pvc", namespace=namespace)
                    if configPVC.status.phase == "Bound":
                        pvcIsBound = True
                    else:
                        logger.debug("Waiting 15s before checking status of config PVC again")
                        logger.debug(configPVC)
                        sleep(15)
            else:
                logger.info(f"Storage class {storageClass} uses volumeBindingMode={volumeBindingMode}, skipping config PVC bind wait")

        # Create backup PVC if requested
        if createBackupPVC:
            logger.info("Creating backup PVC")
            backupTemplate = env.get_template("pipelines-backup-pvc.yml.j2")
            renderedBackupTemplate = backupTemplate.render(
                mas_instance_id=instanceId,
                pipeline_storage_class=storageClass,
                pipeline_storage_accessmode=accessMode,
                backup_storage_size=backupStorageSize,
            )
            logger.debug(renderedBackupTemplate)
            backupPvc = yaml.safe_load(renderedBackupTemplate)
            pvcAPI.apply(body=backupPvc, namespace=namespace)

            if waitForBind:
                logger.info(f"Storage class {storageClass} uses volumeBindingMode={volumeBindingMode}, waiting for backup PVC to bind")
                backupPvcIsBound = False
                while not backupPvcIsBound:
                    backupPVC = pvcAPI.get(name="backup-pvc", namespace=namespace)
                    if backupPVC.status.phase == "Bound":
                        backupPvcIsBound = True
                    else:
                        logger.debug("Waiting 15s before checking status of backup PVC again")
                        logger.debug(backupPVC)
                        sleep(15)
            else:
                logger.info(f"Storage class {storageClass} uses volumeBindingMode={volumeBindingMode}, skipping backup PVC bind wait")


def prepareAiServicePipelinesNamespace(
    dynClient: DynamicClient,
    instanceId: str = None,
    storageClass: str = None,
    accessMode: str = None,
    waitForBind: bool = True,
    configureRBAC: bool = True,
):
    """
    Prepare a namespace for AI Service pipelines by creating RBAC and PVC resources.

    Creates AI Service-specific pipeline namespace with necessary role bindings
    and persistent volume claims.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        instanceId (str, optional): AI Service instance ID. Defaults to None.
        storageClass (str, optional): Storage class for the PVC. Defaults to None.
        accessMode (str, optional): Access mode for the PVC. Defaults to None.
        waitForBind (bool, optional): Whether to wait for PVC to bind. Defaults to True.
        configureRBAC (bool, optional): Whether to configure RBAC. Defaults to True.

    Returns:
        None

    Raises:
        NotFoundError: If resources cannot be created
    """
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(loader=FileSystemLoader(searchpath=templateDir))
    namespace = f"aiservice-{instanceId}-pipelines"
    template = env.get_template("aiservice-pipelines-rbac.yml.j2")

    if configureRBAC:
        # Create RBAC
        renderedTemplate = template.render(aiservice_instance_id=instanceId)
        logger.debug(renderedTemplate)
        crb = yaml.safe_load(renderedTemplate)
        clusterRoleBindingAPI = dynClient.resources.get(api_version="rbac.authorization.k8s.io/v1", kind="ClusterRoleBinding")
        clusterRoleBindingAPI.apply(body=crb, namespace=namespace)

    template = env.get_template("aiservice-pipelines-pvc.yml.j2")
    renderedTemplate = template.render(
        aiservice_instance_id=instanceId,
        pipeline_storage_class=storageClass,
        pipeline_storage_accessmode=accessMode,
    )
    logger.debug(renderedTemplate)
    pvc = yaml.safe_load(renderedTemplate)
    pvcAPI = dynClient.resources.get(api_version="v1", kind="PersistentVolumeClaim")
    pvcAPI.apply(body=pvc, namespace=namespace)

    # Automatically determine if we should wait for PVC binding based on storage class
    volumeBindingMode = getStorageClassVolumeBindingMode(dynClient, storageClass)
    waitForBind = volumeBindingMode == "Immediate"

    if waitForBind:
        logger.info(f"Storage class {storageClass} uses volumeBindingMode={volumeBindingMode}, waiting for PVC to bind")
        pvcIsBound = False
        while not pvcIsBound:
            configPVC = pvcAPI.get(name="config-pvc", namespace=namespace)
            if configPVC.status.phase == "Bound":
                pvcIsBound = True
            else:
                logger.debug("Waiting 15s before checking status of PVC again")
                logger.debug(configPVC)
                sleep(15)
    else:
        logger.info(f"Storage class {storageClass} uses volumeBindingMode={volumeBindingMode}, skipping PVC bind wait")


def prepareRestoreSecrets(dynClient: DynamicClient, namespace: str, restoreConfigs: dict = None):
    """
    Create or update secret required for MAS Restore pipeline.

    Creates secret in the specified namespace:
        - pipeline-restore-configs

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to create secrets in
        restoreConfigs (dict, optional): configuration data for restore. Defaults to None (empty secret).

    Returns:
        None

    Raises:
        NotFoundError: If secrets cannot be created
    """
    secretsAPI = dynClient.resources.get(api_version="v1", kind="Secret")

    # 1. Secret/pipeline-restore-configs
    # -------------------------------------------------------------------------
    # Must exist, but can be empty
    try:
        secretsAPI.delete(name="pipeline-restore-configs", namespace=namespace)
    except NotFoundError:
        pass

    if restoreConfigs is None:
        restoreConfigs = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {"name": "pipeline-restore-configs"},
        }
    secretsAPI.create(body=restoreConfigs, namespace=namespace)


def prepareInstallSecrets(
    dynClient: DynamicClient,
    namespace: str,
    slsLicenseFile: str = None,
    additionalConfigs: dict = None,
    certs: str = None,
    podTemplates: str = None,
    slack_token: str = None,
    slack_channel: str = None,
    aiserviceConfig: str = None,
    db2LicenseFile: dict | None = None,
    facilitiesProperties: dict | None = None,
) -> None:
    """
    Create or update secrets required for MAS installation pipelines.

    Creates secrets in the specified namespace: mas-devops-slack, pipeline-additional-configs,
    pipeline-sls-entitlement, pipeline-certificates, pipeline-pod-templates, pipeline-aiservice-config,
    pipeline-db2-license, and pipeline-facilities-properties.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to create secrets in (format: mas-{instance_id}-pipelines or aiservice-{instance_id}-pipelines)
        slsLicenseFile (dict, optional): SLS license file content. Defaults to None (empty secret).
        db2LicenseFile (dict, optional): Db2 license file content. Defaults to None (empty secret).
        additionalConfigs (dict, optional): Additional configuration data. Defaults to None (empty secret).
        certs (str, optional): Certificate data. Defaults to None (empty secret).
        podTemplates (str, optional): Pod template data. Defaults to None (empty secret).
        slack_token (str, optional): Slack bot token for notifications. Defaults to None.
        slack_channel (str, optional): Slack channel ID for notifications. Defaults to None.
        aiserviceConfig (str, optional): AI Service tenant config data. Defaults to None (empty secret).
        facilitiesProperties (dict, optional): Facilities properties file content. Defaults to None (empty secret).

    Returns:
        None

    Raises:
        NotFoundError: If secrets cannot be created
    """
    secretsAPI = dynClient.resources.get(api_version="v1", kind="Secret")

    # Extract instance ID from namespace using regex
    # Supports both formats: mas-{instance_id}-pipelines and aiservice-{instance_id}-pipelines
    instance_id = None
    namespace_pattern = r"^(?:mas|aiservice)-(.+)-pipelines$"
    match = re.match(namespace_pattern, namespace)
    if match:
        instance_id = match.group(1)

    # 0. Secret/mas-devops-slack
    # -------------------------------------------------------------------------
    # Create mas-devops-slack secret with MAS_INSTANCE_ID, SLACK_TOKEN, and SLACK_CHANNEL keys
    if instance_id:
        try:
            secretsAPI.delete(name="mas-devops-slack", namespace=namespace)
        except NotFoundError:
            pass

        secret_data = {"MAS_INSTANCE_ID": base64.b64encode(instance_id.encode()).decode()}

        # Add slack_token if provided
        if slack_token:
            secret_data["SLACK_TOKEN"] = base64.b64encode(slack_token.encode()).decode()

        # Add slack_channel if provided
        if slack_channel:
            secret_data["SLACK_CHANNEL"] = base64.b64encode(slack_channel.encode()).decode()

        mas_devops_secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {"name": "mas-devops-slack"},
            "data": secret_data,
        }
        secretsAPI.create(body=mas_devops_secret, namespace=namespace)
        logger.info(f"Created mas-devops-slack secret with MAS_INSTANCE_ID={instance_id} in namespace {namespace}")

    # 1. Secret/pipeline-additional-configs
    # -------------------------------------------------------------------------
    # Must exist, but can be empty
    try:
        secretsAPI.delete(name="pipeline-additional-configs", namespace=namespace)
    except NotFoundError:
        pass

    if additionalConfigs is None:
        additionalConfigs = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {"name": "pipeline-additional-configs"},
        }
    secretsAPI.create(body=additionalConfigs, namespace=namespace)

    # 2. Secret/pipeline-sls-entitlement
    # -------------------------------------------------------------------------
    try:
        secretsAPI.delete(name="pipeline-sls-entitlement", namespace=namespace)
    except NotFoundError:
        pass

    if slsLicenseFile is None:
        slsLicenseFile = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {"name": "pipeline-sls-entitlement"},
        }
    secretsAPI.create(body=slsLicenseFile, namespace=namespace)

    # 3. Secret/pipeline-certificates
    # -------------------------------------------------------------------------
    # Must exist. It could be an empty secret at the first place before customer configure it
    try:
        secretsAPI.delete(name="pipeline-certificates", namespace=namespace)
    except NotFoundError:
        pass

    if certs is None:
        certs = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {"name": "pipeline-certificates"},
        }
    secretsAPI.create(body=certs, namespace=namespace)

    # 4. Secret/pipeline-pod-templates
    # -------------------------------------------------------------------------
    # Must exist, but can be empty
    try:
        secretsAPI.delete(name="pipeline-pod-templates", namespace=namespace)
    except NotFoundError:
        pass

    if podTemplates is None:
        podTemplates = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {"name": "pipeline-pod-templates"},
        }
    secretsAPI.create(body=podTemplates, namespace=namespace)

    # 5. Secret/pipeline-aiservice-config
    # -------------------------------------------------------------------------
    try:
        secretsAPI.delete(name="pipeline-aiservice-config", namespace=namespace)
    except NotFoundError:
        pass

    if aiserviceConfig is None:
        aiserviceConfig = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {"name": "pipeline-aiservice-config"},
        }
    secretsAPI.create(body=aiserviceConfig, namespace=namespace)

    # 6. Secret/pipeline-db2-license
    # -------------------------------------------------------------------------
    try:
        secretsAPI.delete(name="pipeline-db2-license", namespace=namespace)
    except NotFoundError:
        pass

    if db2LicenseFile is None:
        db2LicenseFile = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {"name": "pipeline-db2-license"},
        }
    secretsAPI.create(body=db2LicenseFile, namespace=namespace)

    # 7. Secret/pipeline-facilities-properties
    # -------------------------------------------------------------------------
    # Only create secret if custom facilities properties are provided
    if facilitiesProperties is not None:
        try:
            secretsAPI.delete(name="pipeline-facilities-properties", namespace=namespace)
        except NotFoundError:
            pass
        secretsAPI.create(body=facilitiesProperties, namespace=namespace)


def prepareUpdateSecrets(
    dynClient: DynamicClient,
    slack_token: str = None,
    slack_channel: str = None,
    db2LicenseFile: dict | None = None,
) -> None:
    """
    Create or update mas-devops-slack secret in mas-pipelines namespace for update pipeline.

    Creates the slack secret in mas-pipelines namespace if it exists and slack credentials are provided.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        slack_token (str, optional): Slack bot token for notifications. Defaults to None.
        slack_channel (str, optional): Slack channel ID for notifications. Defaults to None.
        db2LicenseFile (dict, optional): Db2 license file content. Defaults to None (empty secret).

    Returns:
        None

    Raises:
        NotFoundError: If namespace doesn't exist (will be caught and logged)
    """
    namespace = "mas-pipelines"

    # Check if namespace exists
    try:
        namespaceAPI = dynClient.resources.get(api_version="v1", kind="Namespace")
        namespaceAPI.get(name=namespace)
    except NotFoundError:
        logger.warning(f"Namespace {namespace} does not exist, skipping slack secret creation")
        return

    # Only create secret if both slack_token and slack_channel are provided
    if not slack_token or not slack_channel:
        logger.debug("Slack token or channel not provided, skipping slack secret creation")

    secretsAPI = dynClient.resources.get(api_version="v1", kind="Secret")

    # Delete existing secret if it exists
    try:
        secretsAPI.delete(name="mas-devops-slack", namespace=namespace)
    except NotFoundError:
        pass

    # Create the secret with SLACK_TOKEN and SLACK_CHANNEL
    secret_data = {}

    if slack_token:
        secret_data["SLACK_TOKEN"] = base64.b64encode(slack_token.encode()).decode()

    if slack_channel:
        secret_data["SLACK_CHANNEL"] = base64.b64encode(slack_channel.encode()).decode()

    mas_devops_secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
        "metadata": {"name": "mas-devops-slack"},
        "data": secret_data,
    }

    secretsAPI.create(body=mas_devops_secret, namespace=namespace)
    logger.info(f"Created mas-devops-slack secret in namespace {namespace}")

    try:
        secretsAPI.delete(name="pipeline-db2-license", namespace=namespace)
    except NotFoundError:
        pass

    if db2LicenseFile is None:
        db2LicenseFile = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {"name": "pipeline-db2-license"},
        }
    secretsAPI.create(body=db2LicenseFile, namespace=namespace)
    logger.info(f"Created pipeline-db2-license secret in namespace {namespace}")


def testCLI() -> None:
    pass
    # echo -n "Testing availability of $CLI_IMAGE in cluster ..."
    # EXISTING_DEPLOYMENT_IMAGE=$(oc -n $PIPELINES_NS get deployment mas-cli -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null)

    # if [[ "$EXISTING_DEPLOYMENT_IMAGE" != "CLI_IMAGE" ]]
    # then oc -n $PIPELINES_NS apply -f $CONFIG_DIR/deployment-$MAS_INSTANCE_ID.yaml &>> $LOGFILE
    # fi

    # oc -n $PIPELINES_NS wait --for=condition=Available=true deployment mas-cli --timeout=3m &>> $LOGFILE
    # if [[ "$?" == "0" ]]; then
    #     # All is good
    #     echo -en "\033[1K" # Clear current line
    #     echo -en "\033[u" # Restore cursor position
    #     echo -e "${COLOR_GREEN}$CLI_IMAGE is available from the target OCP cluster${TEXT_RESET}"
    # else
    #     echo -en "\033[1K" # Clear current line
    #     echo -en "\033[u" # Restore cursor position

    #     # We can't get the image, so there's no point running the pipeline
    #     echo_warning "Failed to validate $CLI_IMAGE in the target OCP cluster"
    #     echo "This image must be accessible from your OpenShift cluster to run the installation:"
    #     echo "- If you are running an offline (air gap) installation this likely means you have not mirrored this image to your private registry"
    #     echo "- It could also mean that your cluster's ImageContentSourcePolicy is misconfigured and does not contain an entry for quay.io/ibmmas"
    #     echo "- Check the deployment status of mas-cli in your pipeline namespace. This will provide you with more information about the issue."

    #     echo -e "\n\n[WARNING] Failed to validate $CLI_IMAGE in the target OCP cluster" >> $LOGFILE
    #     echo_hr1 >> $LOGFILE
    #     oc -n $PIPELINES_NS get pods --selector="app=mas-cli" -o yaml >> $LOGFILE
    #     exit 1
    # fi


def launchUpgradePipeline(
    dynClient: DynamicClient,
    instanceId: str,
    skipPreCheck: bool = False,
    masChannel: str = "",
    params: dict = {},
) -> str:
    """
    Create a PipelineRun to upgrade the chosen MAS instance
    """
    pipelineRunsAPI = dynClient.resources.get(api_version="tekton.dev/v1beta1", kind="PipelineRun")
    namespace = f"mas-{instanceId}-pipelines"
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    # Create the PipelineRun
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(loader=FileSystemLoader(searchpath=templateDir))
    template = env.get_template("pipelinerun-upgrade.yml.j2")
    renderedTemplate = template.render(
        timestamp=timestamp,
        mas_instance_id=instanceId,
        skip_pre_check=skipPreCheck,
        mas_channel=masChannel,
        **params,
    )
    logger.debug(renderedTemplate)
    pipelineRun = yaml.safe_load(renderedTemplate)
    pipelineRunsAPI.apply(body=pipelineRun, namespace=namespace)

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/mas-{instanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{instanceId}-upgrade-{timestamp}"
    return pipelineURL


def launchUninstallPipeline(
    dynClient: DynamicClient,
    instanceId: str,
    droNamespace: str,
    uninstallCertManager: bool = False,
    uninstallGrafana: bool = False,
    uninstallCatalog: bool = False,
    uninstallDRO: bool = False,
    uninstallMongoDb: bool = False,
    uninstallSLS: bool = False,
) -> str:
    """
    Create a PipelineRun to uninstall the chosen MAS instance (and selected dependencies)
    """
    pipelineRunsAPI = dynClient.resources.get(api_version="tekton.dev/v1beta1", kind="PipelineRun")
    namespace = f"mas-{instanceId}-pipelines"
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    # Create the PipelineRun
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(loader=FileSystemLoader(searchpath=templateDir))
    template = env.get_template("pipelinerun-uninstall.yml.j2")

    grafanaAction = "uninstall" if uninstallGrafana else "none"
    certManagerAction = "uninstall" if uninstallCertManager else "none"
    ibmCatalogAction = "uninstall" if uninstallCatalog else "none"
    mongoDbAction = "uninstall" if uninstallMongoDb else "none"
    slsAction = "uninstall" if uninstallSLS else "none"
    droAction = "uninstall" if uninstallDRO else "none"

    # Render the pipelineRun
    renderedTemplate = template.render(
        timestamp=timestamp,
        mas_instance_id=instanceId,
        grafana_action=grafanaAction,
        cert_manager_action=certManagerAction,
        ibm_catalogs_action=ibmCatalogAction,
        mongodb_action=mongoDbAction,
        sls_action=slsAction,
        dro_action=droAction,
        dro_namespace=droNamespace,
    )
    logger.debug(renderedTemplate)
    pipelineRun = yaml.safe_load(renderedTemplate)
    pipelineRunsAPI.apply(body=pipelineRun, namespace=namespace)

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/mas-{instanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{instanceId}-uninstall-{timestamp}"
    return pipelineURL


def launchPipelineRun(dynClient: DynamicClient, namespace: str, templateName: str, params: dict) -> str:
    """
    Launch a Tekton PipelineRun from a template.

    Creates a PipelineRun resource by rendering a Jinja2 template with the provided parameters.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to create the PipelineRun in
        templateName (str): Name of the template file (without .yml.j2 extension)
        params (dict): Parameters to pass to the template

    Returns:
        str: Timestamp string used in the PipelineRun name (format: YYMMDD-HHMM)

    Raises:
        NotFoundError: If the template or namespace is not found
    """
    pipelineRunsAPI = dynClient.resources.get(api_version="tekton.dev/v1beta1", kind="PipelineRun")
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    # Create the PipelineRun
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(loader=FileSystemLoader(searchpath=templateDir))
    template = env.get_template(f"{templateName}.yml.j2")

    # Render the pipelineRun
    renderedTemplate = template.render(timestamp=timestamp, **params)
    logger.debug(renderedTemplate)
    pipelineRun = yaml.safe_load(renderedTemplate)
    pipelineRunsAPI.apply(body=pipelineRun, namespace=namespace)
    return timestamp


def launchInstallPipeline(dynClient: DynamicClient, params: dict) -> str:
    """
    Create a PipelineRun to install a MAS or AI Service instance with selected dependencies.

    Automatically detects whether to install MAS or AI Service based on the presence
    of mas_instance_id in params.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        params (dict): Installation parameters including instance ID and configuration

    Returns:
        str: URL to the PipelineRun in the OpenShift console

    Raises:
        NotFoundError: If resources cannot be created
    """
    applicationType = "aiservice" if not params.get("mas_instance_id") else "mas"
    params["applicationType"] = applicationType
    instanceId = params[f"{applicationType}_instance_id"]
    namespace = f"{applicationType}-{instanceId}-pipelines"
    timestamp = launchPipelineRun(dynClient, namespace, "pipelinerun-install", params)

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/{applicationType}-{instanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{instanceId}-install-{timestamp}"
    return pipelineURL


def launchUpdatePipeline(dynClient: DynamicClient, params: dict) -> str:
    """
    Create a PipelineRun to update the Maximo Operator Catalog.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        params (dict): Update parameters

    Returns:
        str: URL to the PipelineRun in the OpenShift console

    Raises:
        NotFoundError: If resources cannot be created
    """
    namespace = "mas-pipelines"
    timestamp = launchPipelineRun(dynClient, namespace, "pipelinerun-update", params)

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/mas-pipelines/tekton.dev~v1beta1~PipelineRun/mas-update-{timestamp}"
    return pipelineURL


def launchDb2MigrationPipeline(dynClient: DynamicClient, params: dict) -> str:
    """
    Create a PipelineRun to migrate Db2uCluster to Db2uInstance.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        params (dict): Migration parameters including:
            - db2_migration_namespace: Target namespace
            - db2_migration_cluster_name: Cluster to migrate
            - db2_migration_backup_enabled: Whether to backup

    Returns:
        str: URL to the PipelineRun in the OpenShift console

    Raises:
        NotFoundError: If resources cannot be created
    """
    namespace = "mas-pipelines"
    timestamp = launchPipelineRun(dynClient, namespace, "pipelinerun-db2-migration", params)

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/mas-pipelines/tekton.dev~v1beta1~PipelineRun/db2-migration-{timestamp}"
    return pipelineURL


def launchBackupPipeline(dynClient: DynamicClient, params: dict) -> str:
    """
    Create a PipelineRun to backup a MAS instance.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        params (dict): Backup parameters including instance ID and configuration

    Returns:
        str: URL to the PipelineRun in the OpenShift console

    Raises:
        NotFoundError: If resources cannot be created
    """
    instanceId = params["mas_instance_id"]
    backupVersion = params["backup_version"]
    namespace = f"mas-{instanceId}-pipelines"
    timestamp = launchPipelineRun(dynClient, namespace, "pipelinerun-backup", params)

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/mas-{instanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{instanceId}-backup-{backupVersion}-{timestamp}"
    return pipelineURL


def launchRestorePipeline(dynClient: DynamicClient, params: dict) -> str:
    """
    Create a PipelineRun to restore a MAS instance.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        params (dict): Backup/Restore parameters including instance ID and configuration

    Returns:
        str: URL to the PipelineRun in the OpenShift console

    Raises:
        NotFoundError: If resources cannot be created
    """
    instanceId = params["mas_instance_id"]
    restoreVersion = params["restore_version"]
    namespace = f"mas-{instanceId}-pipelines"
    timestamp = launchPipelineRun(dynClient, namespace, "pipelinerun-restore", params)

    pipelineURL = (
        f"{getConsoleURL(dynClient)}/k8s/ns/mas-{instanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{instanceId}-restore-{restoreVersion}-{timestamp}"
    )
    return pipelineURL


def launchAiServiceUpgradePipeline(
    dynClient: DynamicClient,
    aiserviceInstanceId: str,
    skipPreCheck: bool = False,
    aiserviceChannel: str = "",
    params: dict = {},
) -> str:
    """
    Create a PipelineRun to upgrade the chosen AI Service instance
    """
    pipelineRunsAPI = dynClient.resources.get(api_version="tekton.dev/v1beta1", kind="PipelineRun")
    namespace = f"aiservice-{aiserviceInstanceId}-pipelines"
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    # Create the PipelineRun
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(loader=FileSystemLoader(searchpath=templateDir))
    template = env.get_template("pipelinerun-aiservice-upgrade.yml.j2")
    renderedTemplate = template.render(
        timestamp=timestamp,
        aiservice_instance_id=aiserviceInstanceId,
        skip_pre_check=skipPreCheck,
        aiservice_channel=aiserviceChannel,
        **params,
    )
    logger.debug(renderedTemplate)
    pipelineRun = yaml.safe_load(renderedTemplate)
    pipelineRunsAPI.apply(body=pipelineRun, namespace=namespace)

    pipelineURL = (
        f"{getConsoleURL(dynClient)}/k8s/ns/aiservice-{aiserviceInstanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{aiserviceInstanceId}-upgrade-{timestamp}"
    )
    return pipelineURL


def prepareInstallRBAC(dynClient: DynamicClient, namespace: str, instanceId: str, installRBACDir: str) -> None:
    """
    Apply the minimal install RBAC bundle for a MAS instance.

    The bundle is defined by the kustomization under cli/rbac/install and creates the install-user and install-pipeline service accounts
    and their associated role bindings.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        instanceId (str): MAS instance ID used to render the RBAC templates
        installRBACDir (str): Path to the directory containing the RBAC kustomization and templates

    Returns:
        None

    Raises:
        FileNotFoundError: If the RBAC bundle directory or kustomization file does not exists
    """
    kustomizationFile = path.join(installRBACDir, "kustomization.yaml")
    if not path.isfile(kustomizationFile):
        logger.error(f"Cannot find kustomization file for install RBAC at {kustomizationFile}")
        raise FileNotFoundError(f"Cannot find kustomization file for install RBAC at {kustomizationFile}")

    with open(kustomizationFile, "r") as file:
        kustomization = yaml.safe_load(file)

    env = Environment()
    for resourcePath in kustomization.get("resources", []):
        manifestFile = path.join(installRBACDir, resourcePath)
        if not path.isfile(manifestFile):
            logger.error(f"Cannot find RBAC manifest file at {manifestFile}")
            raise FileNotFoundError(f"Cannot find RBAC manifest file at {manifestFile}")

        with open(manifestFile, "r") as file:
            template = env.from_string(file.read())
            renderedManifest = template.render(mas_instance_id=instanceId)
            logger.debug(f"Applying RBAC manifest {manifestFile} for instance {instanceId}:\n{renderedManifest}")

        for resourceBody in yaml.safe_load_all(renderedManifest):
            if resourceBody is None:
                continue

            apiVersion = resourceBody["apiVersion"]
            kind = resourceBody["kind"]
            metadata = resourceBody.get("metadata", {})
            name = metadata.get("name", "<unnamed>")
            namespace = metadata.get("namespace")

            logger.debug(f"Applying RBAC resource {kind}/{name} in namespace {namespace} for instance {instanceId}")
            resourceAPI = dynClient.resources.get(api_version=apiVersion, kind=kind)

            # Optimized retry logic for transient API server errors
            max_retries = 10  # Reduced from 30 to 10 retries
            base_delay = 1  # Reduced initial delay from 2s to 1s
            max_delay = 15  # Reduced max delay from 30s to 15s

            for attempt in range(max_retries):
                try:
                    if namespace:
                        resourceAPI.apply(body=resourceBody, namespace=namespace)
                    else:
                        resourceAPI.apply(body=resourceBody)

                    # Log success only if there were previous failures
                    if attempt > 0:
                        logger.info(f"Successfully applied {kind}/{name} after {attempt + 1} attempts")
                    break  # Success, exit retry loop

                except ApiException as e:
                    # Check if it's a retryable error (429, 503, 504, or API server shutdown)
                    is_retryable = (
                        e.status in [429, 503, 504]
                        or "apiserver is shutting down" in str(e).lower()
                        or "connection refused" in str(e).lower()
                        or "too many requests" in str(e).lower()
                    )

                    if is_retryable and attempt < max_retries - 1:
                        # Exponential backoff with jitter to avoid thundering herd
                        import random

                        wait_time = min(base_delay * (2**attempt), max_delay)
                        jitter = random.uniform(0, 0.1 * wait_time)  # Add up to 10% jitter
                        total_wait = wait_time + jitter

                        logger.warning(
                            f"API server temporarily unavailable for {kind}/{name} "
                            f"(attempt {attempt + 1}/{max_retries}, status: {e.status}). "
                            f"Retrying in {total_wait:.1f}s..."
                        )
                        sleep(total_wait)
                    elif is_retryable:
                        # Exhausted all retries
                        logger.error(
                            f"Failed to apply RBAC resource {kind}/{name} after {max_retries} attempts. "
                            f"API server may be unavailable. Last error: {e.status} - {str(e)[:200]}"
                        )
                        raise
                    else:
                        # Non-retryable error (permissions, invalid resource, etc.)
                        logger.error(f"Failed to apply RBAC resource {kind}/{name}: {e.status} - {str(e)[:200]}")
                        raise

                except Exception as e:
                    # Catch any other unexpected errors
                    logger.error(f"Unexpected error applying RBAC resource {kind}/{name}: {type(e).__name__} - {str(e)[:200]}")
                    raise
