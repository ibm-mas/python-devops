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
from os import path
from types import SimpleNamespace
from kubernetes.dynamic.resource import ResourceInstance
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError, ResourceNotFoundError, UnauthorizedError
from jinja2 import Environment, FileSystemLoader

from ..ocp import getStorageClasses, listInstances
from ..olm import getSubscription

logger = logging.getLogger(__name__)


def isAirgapInstall(dynClient: DynamicClient, checkICSP: bool = False) -> bool:
    """
    Determine if MAS is installed in an air-gapped (disconnected) environment.

    This function checks for the presence of ImageDigestMirrorSet (IDMS) or
    ImageContentSourcePolicy (ICSP) resources that indicate mirror registries
    are configured for air-gapped installations.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        checkICSP (bool, optional): If True, check for legacy ICSP resources instead of IDMS.
                                   Defaults to False (checks IDMS).

    Returns:
        bool: True if air-gap configuration is detected, False otherwise.
    """
    if checkICSP:
        try:
            ICSPApi = dynClient.resources.get(api_version="operator.openshift.io/v1alpha1", kind="ImageContentSourcePolicy")
            ICSPApi.get(name="ibm-mas-and-dependencies")
            return True
        except NotFoundError:
            return False
    else:
        IDMSApi = dynClient.resources.get(api_version="config.openshift.io/v1", kind="ImageDigestMirrorSet")
        masIDMS = IDMSApi.get(label_selector="mas.ibm.com/idmsContent=ibm")
        aiserviceIDMS = IDMSApi.get(label_selector="aiservice.ibm.com/idmsContent=ibm")
        return len(masIDMS.items) + len(aiserviceIDMS.items) > 0


def getDefaultStorageClasses(dynClient: DynamicClient) -> dict:
    """
    Detect and return default storage classes for the cluster environment.

    This function identifies the storage provider (IBM Cloud, OCS, Azure, AWS, etc.)
    by examining available storage classes and returns appropriate RWO (ReadWriteOnce)
    and RWX (ReadWriteMany) storage class names.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.

    Returns:
        SimpleNamespace: Object with attributes:
                        - provider (str): Provider identifier (e.g., "ibmc", "ocs", "aws")
                        - providerName (str): Human-readable provider name
                        - rwo (str): Storage class name for RWO volumes
                        - rwx (str): Storage class name for RWX volumes
                        All attributes are None if no recognized provider is found.
    """
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
        elif storageClass.metadata.name == "longhorn":
            result.provider = "longhorn"
            result.providerName = "Longhorn"
            result.rwo = "longhorn"
            result.rwx = "longhorn"
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
    """
    Retrieve information about the currently installed IBM Operator Catalog.

    This function queries the ibm-operator-catalog CatalogSource and extracts
    version information from its display name and image reference.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.

    Returns:
        dict: Dictionary with keys:
             - displayName (str): Catalog display name
             - image (str): Catalog image reference
             - catalogId (str): Parsed catalog identifier (e.g., "v9-241205-amd64")
             Returns None if the catalog is not found.
    """
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
    Retrieve all MAS Suite instances from the OpenShift cluster.

    This function queries the cluster for Suite custom resources and returns
    a list of all MAS instances found.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.

    Returns:
        list: A list of dictionaries representing MAS Suite instances.
              Returns an empty list if no instances are found or if errors occur.
    """
    return listInstances(dynClient, "core.mas.ibm.com/v1", "Suite")


def getWorkspaceId(dynClient: DynamicClient, instanceId: str) -> str:
    """
    Retrieve the workspace ID for a MAS instance.

    This function queries the Workspace custom resources in the MAS core namespace
    and returns the workspace ID from the first workspace found.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        instanceId (str): The MAS instance identifier.

    Returns:
        str: The workspace ID if found, None if no workspaces exist for the instance.
    """
    workspaceId = None
    workspacesAPI = dynClient.resources.get(api_version="core.mas.ibm.com/v1", kind="Workspace")
    workspaces = workspacesAPI.get(namespace=f"mas-{instanceId}-core")
    if len(workspaces["items"]) > 0:
        workspaceId = workspaces["items"][0]["metadata"]["labels"]["mas.ibm.com/workspaceId"]
    else:
        logger.info("There are no MAS workspaces for the provided instanceId on this cluster")
    return workspaceId


def verifyMasInstance(dynClient: DynamicClient, instanceId: str) -> bool:
    """
    Verify that a MAS Suite instance exists in the cluster.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        instanceId (str): The MAS instance identifier to verify.

    Returns:
        bool: True if the instance exists and is accessible, False otherwise.
              Returns False if the instance is not found, the CRD doesn't exist,
              or authorization fails.
    """
    try:
        suitesAPI = dynClient.resources.get(api_version="core.mas.ibm.com/v1", kind="Suite")
        suitesAPI.get(name=instanceId, namespace=f"mas-{instanceId}-core")
        return True
    except NotFoundError:
        return False
    except ResourceNotFoundError:
        # The MAS Suite CRD has not even been installed in the cluster
        return False
    except UnauthorizedError as e:
        logger.error(f"Error: Unable to verify MAS instance due to failed authorization: {e}")
        return False


def getMasChannel(dynClient: DynamicClient, instanceId: str) -> str:
    """
    Retrieve the OLM subscription channel for a MAS instance.

    This function queries the Operator Lifecycle Manager subscription for the
    MAS Core operator to determine which update channel it is subscribed to.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        instanceId (str): The MAS instance identifier.

    Returns:
        str: The channel name (e.g., "8.11.x", "9.0.x") if the subscription exists,
             None if the subscription is not found.
    """
    masSubscription = getSubscription(dynClient, f"mas-{instanceId}-core", "ibm-mas")
    if masSubscription is None:
        return None
    else:
        return masSubscription.spec.channel


def updateIBMEntitlementKey(dynClient: DynamicClient, namespace: str, icrUsername: str, icrPassword: str, artifactoryUsername: str = None, artifactoryPassword: str = None, secretName: str = "ibm-entitlement") -> ResourceInstance:
    """
    Create or update the IBM Entitlement secret for accessing IBM container registries.

    This function generates a Docker config JSON with credentials for IBM Container Registry
    (ICR) and optionally Artifactory, then creates or updates a Kubernetes secret.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        namespace (str): The namespace where the secret should be created/updated.
        icrUsername (str): Username for IBM Container Registry (typically "cp").
        icrPassword (str): Entitlement key for IBM Container Registry.
        artifactoryUsername (str, optional): Username for Artifactory access. Defaults to None.
        artifactoryPassword (str, optional): Password/token for Artifactory access. Defaults to None.
        secretName (str, optional): Name of the secret to create/update. Defaults to "ibm-entitlement".

    Returns:
        ResourceInstance: The created or updated Secret resource.
    """
    if secretName is None:
        secretName = "ibm-entitlement"
    if artifactoryUsername is not None:
        logger.info(f"Updating IBM Entitlement ({secretName}) in namespace '{namespace}' (with Artifactory access)")
    else:
        logger.info(f"Updating IBM Entitlement ({secretName}) in namespace '{namespace}'")

    templateDir = path.join(path.abspath(path.dirname(__file__)), "..", "templates")
    env = Environment(
        loader=FileSystemLoader(searchpath=templateDir),
        extensions=["jinja2_base64_filters.Base64Filters"]
    )

    contentTemplate = env.get_template("ibm-entitlement-dockerconfig.json.j2")
    dockerConfig = contentTemplate.render(
        artifactory_username=artifactoryUsername,
        artifactory_token=artifactoryPassword,
        icr_username=icrUsername,
        icr_password=icrPassword
    )

    template = env.get_template("ibm-entitlement-secret.yml.j2")
    renderedTemplate = template.render(
        name=secretName,
        namespace=namespace,
        docker_config=dockerConfig
    )
    secret = yaml.safe_load(renderedTemplate)
    secretsAPI = dynClient.resources.get(api_version="v1", kind="Secret")

    secret = secretsAPI.apply(body=secret, namespace=namespace)
    return secret
