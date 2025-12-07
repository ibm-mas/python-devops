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
    Get the application or workspace Custom Resource

    :param dynClient: Description
    :type dynClient: DynamicClient
    :param instanceId: Description
    :type instanceId: str
    :param applicationId: Description
    :type applicationId: str
    :return: Description
    :rtype: bool
    :type workspaceId: str
    :return: Description
    :rtype: bool
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
    Validate that the chosen app instance exists
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
    Docstring for waitForAppReady

    :param dynClient: Description
    :type dynClient: DynamicClient
    :param instanceId: Description
    :type instanceId: str
    :param applicationId: Description
    :type applicationId: str
    :param workspaceId: Description
    :type workspaceId: str
    :param retries: Description
    :type retries: int
    :param delay: Description
    :type delay: int
    :return: Description
    :rtype: bool
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
    Return list of installed apps with their subscribed channel
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
