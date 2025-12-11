# *****************************************************************************
# Copyright (c) 2025 IBM Corporation and other Contributors.
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

from .ocp import listInstances
from .olm import getSubscription

logger = logging.getLogger(__name__)


def listAiServiceInstances(dynClient: DynamicClient) -> list:
    """
    Get a list of AI Service instances on the cluster
    """
    return listInstances(dynClient, "aiservice.ibm.com/v1", "AIServiceApp")


def verifyAiServiceInstance(dynClient: DynamicClient, instanceId: str) -> bool:
    """
    Validate that the chosen AI Service instance exists
    """
    try:
        aiserviceAPI = dynClient.resources.get(api_version="aiservice.ibm.com/v1", kind="AIServiceApp")
        aiserviceAPI.get(name=instanceId, namespace=f"aiservice-{instanceId}")
        return True
    except NotFoundError:
        print("NOT FOUND")
        return False
    except ResourceNotFoundError:
        # The AIServiceApp CRD has not even been installed in the cluster
        print("RESOURCE NOT FOUND")
        return False
    except UnauthorizedError as e:
        logger.error(f"Error: Unable to verify AI Service instance due to failed authorization: {e}")
        return False


def getAiserviceChannel(dynClient: DynamicClient, instanceId: str) -> str:
    """
    Get the AI Service channel from the subscription
    """
    aiserviceSubscription = getSubscription(dynClient, f"aiservice-{instanceId}", "ibm-aiservice")
    if aiserviceSubscription is None:
        return None
    else:
        return aiserviceSubscription.spec.channel
