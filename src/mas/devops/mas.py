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
from types import SimpleNamespace
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError, UnauthorizedError

from .ocp import getStorageClasses

logger = logging.getLogger(__name__)


def isAirgapInstall(dynClient: DynamicClient) -> bool:
    try:
        ICSPApi = dynClient.resources.get(api_version="operator.openshift.io/v1alpha1", kind="ImageContentSourcePolicy")
        ICSPApi.get(name="ibm-mas-and-dependencies")
        return True
    except NotFoundError:
        return False


def getDefaultStorageClasses(dynClient: DynamicClient) -> dict:
    result = SimpleNamespace(
        provider=None,
        providerName=None,
        rwo=None,
        rwx=None
    )

    # Iterate through storage classes until we find one that we recognize
    # We make an assumption that if one of the paired classes if available, both will be
    storageClasses = getStorageClasses(dynClient)
    for storageClass in storageClasses:
        if storageClass.metadata.name in ["ibmc-block-gold", "ibmc-file-gold-gid"]:
            result.provider = "ibmc"
            result.providerName = "IBMCloud ROKS"
            result.rwo = "ibmc-block-gold"
            result.rwx = "ibmc-file-gold-gid"
            break
        elif storageClass.metadata.name in ["ocs-storagecluster-ceph-rbd", "ocs-storagecluster-cephfs"]:
            result.provider = "ocs"
            result.providerName = "OpenShift Container Storage"
            result.rwo = "ocs-storagecluster-ceph-rbd"
            result.rwx = "ocs-storagecluster-cephfs"
            break
        elif storageClass.metadata.name in ["ocs-external-storagecluster-ceph-rbd", "ocs-external-storagecluster-cephfs"]:
            result.provider = "ocs-external"
            result.providerName = "OpenShift Container Storage (External)"
            result.rwo = "ocs-external-storagecluster-ceph-rbd"
            result.rwx = "ocs-external-storagecluster-cephfs"
            break
        elif storageClass.metadata.name == "nfs-client":
            result.provider = "nfs"
            result.providerName = "NFS Client"
            result.rwo = "nfs-client"
            result.rwx = "nfs-client"
            break
        elif storageClass.metadata.name in ["managed-premium", "azurefiles-premium"]:
            result.provider = "azure"
            result.providerName = "Azure Managed"
            result.rwo = "managed-premium"
            result.rwx = "azurefiles-premium"
            break
        elif storageClass.metadata.name in ["gp3-csi", "efs"]:
            result.provider = "aws"
            result.providerName = "AWS GP3"
            result.rwo = "gp3-csi"
            result.rwx = "efs"
            break
    logger.debug(f"Default storage class: {result}")
    return result


def getCurrentCatalog(dynClient: DynamicClient) -> dict:
    catalogsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="CatalogSource")
    try:
        catalog = catalogsAPI.get(name="ibm-operator-catalog", namespace="openshift-marketplace")
        catalogDisplayName = catalog.spec.displayName
        catalogImage = catalog.spec.image

        m = re.match(r".+(?P<catalogId>v[89]-(?P<catalogVersion>[0-9]+)-(amd64|s390x|ppc64le))", catalogDisplayName)
        if m:
            # catalogId = v9-yymmdd-amd64
            # catalogVersion = yymmdd
            installedCatalogId = m.group("catalogId")
        elif re.match(r".+v8-amd64", catalogDisplayName):
            installedCatalogId = "v8-amd64"
        else:
            installedCatalogId = None

        return {
            "displayName": catalogDisplayName,
            "image": catalogImage,
            "catalogId": installedCatalogId,
        }
    except NotFoundError:
        return None


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
