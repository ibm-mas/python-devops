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


def getDefaultStorageClasses(dynClient: DynamicClient) -> SimpleNamespace:
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


def getMasPublicClusterIssuer(dynClient: DynamicClient, instanceId: str) -> str | None:
    """
    Retrieve the Public Cluster Issuer for a MAS instance.

    This function queries the Suite custom resource and attempts to retrieve the
    certificate issuer name from spec.certificateIssuer.name. If the keys don't exist,
    it returns the default issuer name.

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        instanceId (str): The MAS instance identifier to use.

    Returns:
        str: The name of the cluster issuer used for the passed in MAS Instance.
             Returns the default "mas-{instanceId}-core-public-issuer" if the suite
             doesn't specify a custom issuer, or None if the suite is not found.
    """
    try:
        suitesAPI = dynClient.resources.get(api_version="core.mas.ibm.com/v1", kind="Suite")
        suite = suitesAPI.get(name=instanceId, namespace=f"mas-{instanceId}-core")

        # Check if spec.certificateIssuer.name exists
        if hasattr(suite, 'spec') and hasattr(suite.spec, 'certificateIssuer') and hasattr(suite.spec.certificateIssuer, 'name'):
            issuerName = suite.spec.certificateIssuer.name
            logger.debug(f"Found custom certificate issuer: {issuerName}")
            return issuerName

        # Keys don't exist, return default
        defaultIssuer = f"mas-{instanceId}-core-public-issuer"
        logger.debug(f"No custom certificate issuer found, using default: {defaultIssuer}")
        return defaultIssuer

    except NotFoundError:
        logger.warning(f"Suite instance '{instanceId}' not found")
        return None
    except ResourceNotFoundError:
        # The MAS Suite CRD has not even been installed in the cluster
        logger.warning("MAS Suite CRD not found in the cluster")
        return None
    except UnauthorizedError as e:
        logger.error(f"Error: Unable to retrieve MAS instance due to failed authorization: {e}")
        return None


def getPermissionMode(dynClient: DynamicClient, instanceId: str) -> str | None:
    """
    Detect the current RBAC permission mode for a MAS instance.

    This function determines whether MAS is installed with cluster-level permissions,
    namespace-scoped permissions (essential + non-essential), or minimal essential-only
    permissions by checking for the existence of RBAC resources in the cluster.

    RBAC Resource Distribution:
    - Cluster mode: ClusterRoles + Essential Roles
    - Namespaced mode: Essential Roles + Non-essential Roles
    - Minimal mode: Essential Roles ONLY

    Detection Logic:
    1. Check for ClusterRoles → cluster mode
    2. Check for non-essential openshift-marketplace Role → namespaced mode
    3. No ClusterRole and no openshift-marketplace Role → minimal mode

    Args:
        dynClient (DynamicClient): OpenShift dynamic client for cluster API interactions.
        instanceId (str): The MAS instance identifier.

    Returns:
        str: Permission mode - "cluster", "namespaced", or "minimal"
             Returns None if unable to determine (e.g., no RBAC resources found)
    """
    try:
        # Step 1: Check for ClusterRoles (indicates cluster mode)
        clusterRoleAPI = dynClient.resources.get(api_version="rbac.authorization.k8s.io/v1", kind="ClusterRole")

        # Look for MAS ClusterRoles with the instance ID pattern
        clusterRoleName = f"mas:{instanceId}:core:coreapi"
        try:
            clusterRoleAPI.get(name=clusterRoleName)
            logger.info(f"Found ClusterRole '{clusterRoleName}' - permission mode is 'cluster'")
            return "cluster"
        except NotFoundError:
            logger.debug(f"ClusterRole '{clusterRoleName}' not found, checking for non-essential Roles")

        # Step 2: Check for non-essential openshift-marketplace Role (only exists in namespaced mode)
        roleAPI = dynClient.resources.get(api_version="rbac.authorization.k8s.io/v1", kind="Role")

        # This role only exists in namespaced mode (applied via role-non-essential-core-coreapi-openshift-marketplace.yaml)
        marketplaceRoleName = f"mas:{instanceId}:core:coreapi:openshift-marketplace"
        marketplaceNamespace = "openshift-marketplace"

        try:
            roleAPI.get(name=marketplaceRoleName, namespace=marketplaceNamespace)
            logger.info(f"Found non-essential Role '{marketplaceRoleName}' in namespace '{marketplaceNamespace}' - permission mode is 'namespaced'")
            return "namespaced"
        except NotFoundError:
            logger.debug("Non-essential openshift-marketplace Role not found, checking for essential roles")

        # Step 3: Verify minimal mode by checking for essential roles in mas-{instanceId}-core namespace
        # Essential roles have pattern: mas:{instanceId}:core:suite:{app}:essential
        coreNamespace = f"mas-{instanceId}-core"

        # Try to find at least one essential role to confirm minimal mode
        # Check common apps that might be installed
        essentialRolePatterns = [
            f"mas:{instanceId}:core:suite:manage:essential",
            f"mas:{instanceId}:core:suite:iot:essential",
            f"mas:{instanceId}:core:suite:monitor:essential",
            f"mas:{instanceId}:core:suite:predict:essential",
            f"mas:{instanceId}:core:suite:arcgis:essential",
            f"mas:{instanceId}:core:suite:facilities:essential",
            f"mas:{instanceId}:core:suite:optimizer:essential",
            f"mas:{instanceId}:core:suite:visualinspection:essential"
        ]

        for essentialRoleName in essentialRolePatterns:
            try:
                roleAPI.get(name=essentialRoleName, namespace=coreNamespace)
                logger.info(f"Found essential Role '{essentialRoleName}' in namespace '{coreNamespace}' with no non-essential roles - permission mode is 'minimal'")
                return "minimal"
            except NotFoundError:
                continue

        # If we couldn't find any RBAC resources, return None
        logger.warning(f"Unable to determine permission mode for instance '{instanceId}' ")
        return None

    except ResourceNotFoundError:
        logger.warning("Required API resources not found in the cluster")
        return None
    except UnauthorizedError as e:
        logger.error(f"Error: Unable to check permissions due to failed authorization: {e}")
        return None
