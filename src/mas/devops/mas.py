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
from openshift.dynamic.exceptions import NotFoundError, UnauthorizedError

logger = logging.getLogger(__name__)


def isAirgapInstall(dynClient: DynamicClient) -> bool:
    try:
        ICSPApi = dynClient.resources.get(api_version="operator.openshift.io/v1alpha1", kind="ImageContentSourcePolicy")
        ICSPApi.get(name="ibm-mas-and-dependencies")
        return True
    except NotFoundError:
        return False


def listMasInstances(dynClient: DynamicClient) -> list:
    """
    Get a list of MAS instances on the cluster
    """
    suitesAPI = dynClient.resources.get(api_version="core.mas.ibm.com/v1", kind="Suite")

    suites = suitesAPI.get().to_dict()['items']
    if len(suites) > 0:
        logger.info(f"There are {len(suites)} MAS instances installed on this cluster:")
        for suite in suites:
            logger.info(f" * {suite['metadata']['name']} v{suite['status']['versions']['reconciled']}")
    else:
        logger.info("There are no MAS instances installed on this cluster")
    return suites


def verifyMasInstance(dynClient: DynamicClient, instanceId: str) -> bool:
    """
    Validate that the chosen MAS instance exists
    """
    try:
        suitesAPI = dynClient.resources.get(api_version="core.mas.ibm.com/v1", kind="Suite")
        suitesAPI.get(name=instanceId, namespace=f"mas-{instanceId}-core")
        return True
    except NotFoundError:
        return False
    except UnauthorizedError:
        logger.error("Error: Unable to verify MAS instance due to failed authorization: {e}")
        return False
