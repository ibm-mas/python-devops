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

logger = logging.getLogger(__name__)


def listSLSInstances(dynClient: DynamicClient) -> list:
    """
    Retrieve all Suite License Service (SLS) instances from the OpenShift cluster.

    This function queries the cluster for LicenseService custom resources and returns
    a list of all SLS instances found. It handles various error conditions gracefully,
    including missing CRDs and authorization failures.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.

    Returns:
        list: A list of dictionaries representing SLS LicenseService instances.
              Returns an empty list if no instances are found, the CRD doesn't exist,
              or authorization fails.

    Raises:
        No exceptions are raised; all errors are caught and logged internally.
    """
    try:
        slsAPI = dynClient.resources.get(api_version="sls.ibm.com/v1", kind="LicenseService")
        return slsAPI.get().to_dict()['items']
    except NotFoundError:
        logger.info("There are no SLS instances installed on this cluster")
        return []
    except ResourceNotFoundError:
        logger.info("LicenseService CRD not found on cluster")
        return []
    except UnauthorizedError:
        logger.error("Error: Unable to verify SLS instances due to failed authorization: {e}")
        return []


def findSLSByNamespace(namespace: str, instances: list = None, dynClient: DynamicClient = None):
    """
    Check if an SLS instance exists in a specific namespace.

    This function searches for Suite License Service instances in the specified namespace.
    It can work with either a pre-fetched list of instances or dynamically query the cluster
    using the provided DynamicClient.

    Args:
        namespace (str): The OpenShift namespace to search for SLS instances.
        instances (list, optional): Pre-fetched list of SLS instance dictionaries.
                                   If None, dynClient must be provided. Defaults to None.
        dynClient (DynamicClient, optional): OpenShift dynamic client for querying instances.
                                            Required if instances is None. Defaults to None.

    Returns:
        bool: True if an SLS instance is found in the specified namespace, False otherwise.
              Also returns False if neither instances nor dynClient is provided.
    """
    if not instances and not dynClient:
        return False

    if not instances and dynClient:
        instances = listSLSInstances(dynClient)

    for instance in instances:
        if namespace in instance['metadata']['namespace']:
            return True
    return False
