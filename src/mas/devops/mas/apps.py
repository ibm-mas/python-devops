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
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError, ResourceNotFoundError, UnauthorizedError

from ..olm import getSubscription

logger = logging.getLogger(__name__)


def verifyAppInstance(dynClient: DynamicClient, instanceId: str, applicationId: str) -> bool:
    """
    Validate that the chosen app instance exists
    """
    try:
        # IoT has a different api version
        operatorApiVersions = dict(iot="iot.ibm.com/v1")
        apiVersion = operatorApiVersions[applicationId] if applicationId in operatorApiVersions else "apps.mas.ibm.com/v1"
        operatorKinds = dict(
            health="HealthApp",
            predict="PredictApp",
            monitor="MonitorApp",
            iot="IoT",
            visualinspection="VisualInspectionApp",
            assist="AssistApp",
            manage="ManageApp",
            optimizer="OptimizerApp",
            facilities="FacilitiesApp",
        )
        appAPI = dynClient.resources.get(api_version=apiVersion, kind=operatorKinds[applicationId])
        appAPI.get(name=instanceId, namespace=f"mas-{instanceId}-{applicationId}")
        return True
    except NotFoundError:
        return False
    except ResourceNotFoundError:
        # The MAS App CRD has not even been installed in the cluster
        return False
    except UnauthorizedError:
        logger.error("Error: Unable to verify MAS app instance due to failed authorization: {e}")
        return False


def getAppsSubscriptionChannel(dynClient: DynamicClient, instanceId: str) -> list:
    """
    Return list of installed apps with their subscribed channel
    """
    try:
        installedApps = []
        appKinds = [
            "assist",
            "facilities",
            "health",
            "hputilities",
            "iot",
            "manage",
            "monitor",
            "mso",
            "optimizer",
            "safety",
            "predict",
            "visualinspection",
            "aibroker"
        ]
        for appKind in appKinds:
            appSubscription = getSubscription(dynClient, f"mas-{instanceId}-{appKind}", f"ibm-mas-{appKind}")
            if appSubscription is not None:
                installedApps.append({"appId": appKind, "channel": appSubscription.spec.channel})
        return installedApps
    except NotFoundError:
        return []
    except ResourceNotFoundError:
        return []
    except UnauthorizedError:
        logger.error("Error: Unable to get MAS app subscriptions due to failed authorization: {e}")
        return []
