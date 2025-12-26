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
import json
from time import sleep
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError, ResourceNotFoundError, UnauthorizedError

from ..olm import getSubscription

logger = logging.getLogger(__name__)

# IoT has a different api version
APP_API_VERSIONS = dict(iot="iot.ibm.com/v1")

APP_IDS = [
    "assist",
    "facilities",
    "iot",
    "manage",
    "monitor",
    "optimizer",
    "predict",
    "visualinspection"
]
APP_KINDS = dict(
    predict="PredictApp",
    monitor="MonitorApp",
    iot="IoT",
    visualinspection="VisualInspectionApp",
    assist="AssistApp",
    manage="ManageApp",
    optimizer="OptimizerApp",
    facilities="FacilitiesApp",
)
APPWS_KINDS = dict(
    predict="PredictWorkspace",
    monitor="MonitorWorkspace",
    iot="IoTWorkspace",
    visualinspection="VisualInspectionAppWorkspace",
    assist="AssistWorkspace",
    manage="ManageWorkspace",
    optimizer="OptimizerWorkspace",
    facilities="FacilitiesWorkspace",
)


def getAppResource(dynClient: DynamicClient, instanceId: str, applicationId: str, workspaceId: str = None) -> bool:
    """
    Retrieve a MAS application or workspace custom resource.

    This function fetches either an application-level CR (e.g., ManageApp) or a
    workspace-level CR (e.g., ManageWorkspace) depending on whether workspaceId is provided.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        instanceId (str): The MAS instance identifier (e.g., "inst1").
        applicationId (str): The MAS application identifier (e.g., "manage", "iot", "monitor").
        workspaceId (str, optional): The workspace identifier. If provided, retrieves workspace CR.
                                    Defaults to None (retrieves application CR).

    Returns:
        ResourceInstance: The custom resource object if found, None otherwise.
                         Returns None if the resource doesn't exist, CRD is missing, or authorization fails.
    """

    apiVersion = APP_API_VERSIONS[applicationId] if applicationId in APP_API_VERSIONS else "apps.mas.ibm.com/v1"
    kind = APP_KINDS[applicationId] if workspaceId is None else APPWS_KINDS[applicationId]
    name = instanceId if workspaceId is None else f"{instanceId}-{workspaceId}"
    namespace = f"mas-{instanceId}-{applicationId}"

    # logger.debug(f"Getting {kind}.{apiVersion} {name} from {namespace}")

    try:
        appAPI = dynClient.resources.get(api_version=apiVersion, kind=kind)
        resource = appAPI.get(name=name, namespace=namespace)
        return resource
    except NotFoundError:
        return None
    except ResourceNotFoundError:
        # The CRD has not even been installed in the cluster
        return None
    except UnauthorizedError as e:
        logger.error(f"Error: Unable to lookup {kind}.{apiVersion} due to authorization failure: {e}")
        return None


def verifyAppInstance(dynClient: DynamicClient, instanceId: str, applicationId: str) -> bool:
    """
    Verify that a MAS application instance exists in the cluster.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        instanceId (str): The MAS instance identifier.
        applicationId (str): The MAS application identifier (e.g., "manage", "iot").

    Returns:
        bool: True if the application instance exists, False otherwise.
    """
    return getAppResource(dynClient, instanceId, applicationId) is not None


def waitForAppReady(
        dynClient: DynamicClient,
        instanceId: str,
        applicationId: str,
        workspaceId: str = None,
        retries: int = 100,
        delay: int = 600,
        debugLogFunction=logger.debug,
        infoLogFunction=logger.info) -> bool:
    """
    Wait for a MAS application or workspace to reach ready state.

    This function polls the application/workspace custom resource until its Ready condition
    status becomes True, or until the retry limit is reached. It checks the status.conditions
    array for a condition with type="Ready" and status="True".

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        instanceId (str): The MAS instance identifier.
        applicationId (str): The MAS application identifier (e.g., "manage", "iot").
        workspaceId (str, optional): The workspace identifier. If provided, waits for workspace CR.
                                    Defaults to None (waits for application CR).
        retries (int, optional): Maximum number of polling attempts. Defaults to 100.
        delay (int, optional): Delay in seconds between polling attempts. Defaults to 600 (10 minutes).
        debugLogFunction (callable, optional): Function for debug logging. Defaults to logger.debug.
        infoLogFunction (callable, optional): Function for info logging. Defaults to logger.info.

    Returns:
        bool: True if the resource reaches ready state within the retry limit, False otherwise.
    """

    resourceName = f"{APP_KINDS[applicationId]}/{instanceId}"
    if workspaceId is not None:
        resourceName = f"{APPWS_KINDS[applicationId]}/{instanceId}-{workspaceId}"

    appCR = None
    appStatus = None

    attempt = 0
    infoLogFunction(f"Polling for {resourceName} to report ready state with {delay}s delay and {retries} retry limit")

    while attempt < retries:
        attempt += 1
        appCR = getAppResource(dynClient, instanceId, applicationId, workspaceId)

        if appCR is None:
            infoLogFunction(f"[{attempt}/{retries}] {resourceName} does not exist")
        else:
            appStatus = appCR.status
            if appStatus is None:
                infoLogFunction(f"[{attempt}/{retries}] {resourceName} has no status")
            else:
                if appStatus.conditions is None:
                    infoLogFunction(f"[{attempt}/{retries}] {resourceName} has no status conditions")
                else:
                    foundReadyCondition: bool = False
                    for condition in appStatus.conditions:
                        if condition.type == "Ready":
                            foundReadyCondition = True
                            if condition.status == "True":
                                infoLogFunction(f"[{attempt}/{retries}] {resourceName} is in ready state: {condition.message}")
                                debugLogFunction(f"{resourceName} status={json.dumps(appStatus.to_dict())}")
                                return True
                            else:
                                infoLogFunction(f"[{attempt}/{retries}] {resourceName} is not in ready state: {condition.message}")
                            continue
                    if not foundReadyCondition:
                        infoLogFunction(f"[{attempt}/{retries}] {resourceName} has no ready status condition")
        sleep(delay)

    # If we made it this far it means that the application was not ready in time
    logger.warning(f"Retry limit reached polling for {resourceName} to report ready state")
    if appStatus is None:
        infoLogFunction(f"No {resourceName} status available")
    else:
        debugLogFunction(f"{resourceName} status={json.dumps(appStatus.to_dict())}")
    return False


def getAppsSubscriptionChannel(dynClient: DynamicClient, instanceId: str) -> list:
    """
    Retrieve the OLM subscription channels for all installed MAS applications.

    This function queries the Operator Lifecycle Manager subscriptions for each known
    MAS application and returns a list of installed applications with their update channels.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        instanceId (str): The MAS instance identifier.

    Returns:
        list: List of dictionaries with 'appId' and 'channel' keys for each installed app.
              Returns empty list if no apps are found or if errors occur.
    """
    try:
        installedApps = []
        for appId in APP_IDS:
            appSubscription = getSubscription(dynClient, f"mas-{instanceId}-{appId}", f"ibm-mas-{appId}")
            if appSubscription is not None:
                installedApps.append({"appId": appId, "channel": appSubscription.spec.channel})
        return installedApps
    except NotFoundError:
        return []
    except ResourceNotFoundError:
        return []
    except UnauthorizedError:
        logger.error("Error: Unable to get MAS app subscriptions due to failed authorization: {e}")
        return []
