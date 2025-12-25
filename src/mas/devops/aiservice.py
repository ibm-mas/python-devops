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
    Retrieve all AI Service instances from the OpenShift cluster.

    This function queries the cluster for AIServiceApp custom resources and returns
    a list of all AI Service instances found.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.

    Returns:
        list: A list of dictionaries representing AI Service instances.
              Returns an empty list if no instances are found or if errors occur.
    """
    return listInstances(dynClient, "aiservice.ibm.com/v1", "AIServiceApp")


def verifyAiServiceInstance(dynClient: DynamicClient, instanceId: str) -> bool:
    """
    Verify that a specific AI Service instance exists in the cluster.

    This function checks if an AIServiceApp custom resource with the given instance ID
    exists in the expected namespace. It handles various error conditions including
    missing instances, missing CRDs, and authorization failures.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        instanceId (str): The unique identifier of the AI Service instance to verify.

    Returns:
        bool: True if the instance exists and is accessible, False otherwise.
              Returns False if the instance is not found, the CRD doesn't exist,
              or authorization fails.
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


def listAiServiceTenantInstances(dynClient: DynamicClient) -> list:
    """
    Retrieve all AI Service Tenant instances from the OpenShift cluster.

    This function queries the cluster for AIServiceTenant custom resources and returns
    a list of all tenant instances found across all AI Service instances.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.

    Returns:
        list: A list of dictionaries representing AI Service Tenant instances.
              Returns an empty list if no tenant instances are found or if errors occur.
    """
    return listInstances(dynClient, "aiservice.ibm.com/v1", "AIServiceTenant")


def verifyAiServiceTenantInstance(dynClient: DynamicClient, instanceId: str, tenantId: str) -> bool:
    """
    Verify that a specific AI Service Tenant exists in the cluster.

    This function checks if an AIServiceTenant custom resource with the given instance ID
    and tenant ID exists in the expected namespace. The tenant resource name follows the
    pattern "aiservice-{instanceId}-{tenantId}".

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        instanceId (str): The unique identifier of the AI Service instance.
        tenantId (str): The unique identifier of the tenant within the AI Service instance.

    Returns:
        bool: True if the tenant exists and is accessible, False otherwise.
              Returns False if the tenant is not found, the CRD doesn't exist,
              or authorization fails.
    """
    try:
        aiserviceTenantAPI = dynClient.resources.get(api_version="aiservice.ibm.com/v1", kind="AIServiceTenant")
        aiserviceTenantAPI.get(name=f"aiservice-{instanceId}-{tenantId}", namespace=f"aiservice-{instanceId}")
        return True
    except NotFoundError:
        print("NOT FOUND")
        return False
    except ResourceNotFoundError:
        # The AIServiceApp CRD has not even been installed in the cluster
        print("RESOURCE NOT FOUND")
        return False
    except UnauthorizedError as e:
        logger.error(f"Error: Unable to verify AI Service Tenant due to failed authorization: {e}")
        return False


def getAiserviceChannel(dynClient: DynamicClient, instanceId: str) -> str | None:
    """
    Retrieve the update channel for an AI Service instance.

    This function queries the Operator Lifecycle Manager (OLM) subscription for the
    AI Service instance to determine which update channel it is subscribed to.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        instanceId (str): The unique identifier of the AI Service instance.

    Returns:
        str: The channel name (e.g., "v1.0", "stable") if the subscription exists,
             None if the subscription is not found.
    """
    aiserviceSubscription = getSubscription(dynClient, f"aiservice-{instanceId}", "ibm-aiservice")
    if aiserviceSubscription is None:
        return None
    else:
        return aiserviceSubscription.spec.channel
