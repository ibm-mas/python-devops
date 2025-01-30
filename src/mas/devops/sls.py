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
    Get a list of SLS instances on the cluster
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
    if not instances and not dynClient:
        return False

    if not instances and dynClient:
        instances = listSLSInstances(dynClient)

    for instance in instances:
        if namespace in instance['metadata']['namespace']:
            return True
    return False
