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
from time import sleep
from types import SimpleNamespace
from kubernetes.dynamic.resource import ResourceInstance
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError, ResourceNotFoundError, UnauthorizedError
from jinja2 import Environment, FileSystemLoader
import semver

from .ocp import getStorageClasses
from .olm import getSubscription

logger = logging.getLogger(__name__)


def isAirgapInstall(dynClient: DynamicClient, checkICSP: bool = False) -> bool:
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
        return len(masIDMS.items) > 0


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
    return listInstances(dynClient, "core.mas.ibm.com/v1", "Suite")


def listAiServiceInstances(dynClient: DynamicClient) -> list:
    """
    Get a list of AI Service instances on the cluster
    """
    return listInstances(dynClient, "aiservice.ibm.com/v1", "AIServiceApp")


def listInstances(dynClient: DynamicClient, apiVersion: str, kind: str) -> list:
    """
    Get a list of instances of a particular CR on the cluster
    """
    api = dynClient.resources.get(api_version=apiVersion, kind=kind)
    instances = api.get().to_dict()['items']
    if len(instances) > 0:
        logger.info(f"There are {len(instances)} {kind} instances installed on this cluster:")
    for instance in instances:
        logger.info(f" * {instance['metadata']['name']} v{instance['status']['versions']['reconciled']}")
    else:
        logger.info(f"There are no {kind} instances installed on this cluster")
    return instances


def getWorkspaceId(dynClient: DynamicClient, instanceId: str) -> str:
    """
    Get the MAS workspace ID for namespace "mas-{instanceId}-core"
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
    Validate that the chosen MAS instance exists
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
            safety="SafetyApp",
            manage="ManageApp",
            hputilities="HPUtilitiesApp",
            mso="MSOApp",
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


def getMasChannel(dynClient: DynamicClient, instanceId: str) -> str:
    """
    Get the MAS channel from the subscription
    """
    masSubscription = getSubscription(dynClient, f"mas-{instanceId}-core", "ibm-mas")
    if masSubscription is None:
        return None
    else:
        return masSubscription.spec.channel


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


def getAiserviceChannel(dynClient: DynamicClient, instanceId: str) -> str:
    """
    Get the AI Service channel from the subscription
    """
    aiserviceSubscription = getSubscription(dynClient, f"aiservice-{instanceId}", "ibm-aiservice")
    if aiserviceSubscription is None:
        return None
    else:
        return aiserviceSubscription.spec.channel


def updateIBMEntitlementKey(dynClient: DynamicClient, namespace: str, icrUsername: str, icrPassword: str, artifactoryUsername: str = None, artifactoryPassword: str = None, secretName: str = "ibm-entitlement") -> ResourceInstance:
    if secretName is None:
        secretName = "ibm-entitlement"
    if artifactoryUsername is not None:
        logger.info(f"Updating IBM Entitlement ({secretName}) in namespace '{namespace}' (with Artifactory access)")
    else:
        logger.info(f"Updating IBM Entitlement ({secretName}) in namespace '{namespace}'")

    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
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


def waitForPVC(dynClient: DynamicClient, namespace: str, pvcName: str) -> bool:
    pvcAPI = dynClient.resources.get(api_version="v1", kind="PersistentVolumeClaim")
    maxRetries = 60
    foundReadyPVC = False
    retries = 0
    while not foundReadyPVC and retries < maxRetries:
        retries += 1
        try:
            pvc = pvcAPI.get(name=pvcName, namespace=namespace)
            if pvc.status.phase == "Bound":
                foundReadyPVC = True
            else:
                logger.debug(f"Waiting 5s for PVC {pvcName} to be ready before checking again ...")
                sleep(5)
        except NotFoundError:
            logger.debug(f"Waiting 5s for PVC {pvcName} to be created before checking again ...")
            sleep(5)

    return foundReadyPVC


def patchPendingPVC(dynClient: DynamicClient, namespace: str, pvcName: str, storageClassName: str = None) -> bool:
    pvcAPI = dynClient.resources.get(api_version="v1", kind="PersistentVolumeClaim")
    try:
        pvc = pvcAPI.get(name=pvcName, namespace=namespace)
        if pvc.status.phase == "Pending" and pvc.spec.storageClassName is None:
            if storageClassName is not None and storageClassName(dynClient, name=storageClassName) is not None:
                pvc.spec.storageClassName = storageClassName
            else:
                defaultStorageClasses = getDefaultStorageClasses(dynClient)
                if defaultStorageClasses.provider is not None:
                    pvc.spec.storageClassName = defaultStorageClasses.rwo
                else:
                    logger.error(f"Unable to set storageClassName in PVC {pvcName}.")
                    return False

            pvcAPI.patch(body=pvc, namespace=namespace)

            maxRetries = 60
            foundReadyPVC = False
            retries = 0
            while not foundReadyPVC and retries < maxRetries:
                retries += 1
                try:
                    patchedPVC = pvcAPI.get(name=pvcName, namespace=namespace)
                    if patchedPVC.status.phase == "Bound":
                        foundReadyPVC = True
                    else:
                        logger.debug(f"Waiting 5s for PVC {pvcName} to be bound before checking again ...")
                        sleep(5)
                except NotFoundError:
                    logger.error(f"The patched PVC {pvcName} does not exist.")
                    return False

            return foundReadyPVC

    except NotFoundError:
        logger.error(f"PVC {pvcName} does not exist")
        return False


def isVersionBefore(_compare_to_version, _current_version):
    """
    The method does a modified semantic version comparison,
    as we want to treat any pre-release as == to the real release
    but in strict semantic versioning it is <
    ie. '8.6.0-pre.m1dev86' is converted to '8.6.0'
    """
    if _current_version is None:
        print("Version is not informed. Returning False")
        return False

    strippedVersion = _current_version.split("-")[0]
    if '.x' in strippedVersion:
        strippedVersion = strippedVersion.replace('.x', '.0')
    current_version = semver.VersionInfo.parse(strippedVersion)
    compareToVersion = semver.VersionInfo.parse(_compare_to_version)
    return current_version.compare(compareToVersion) < 0


def isVersionEqualOrAfter(_compare_to_version, _current_version):
    """
    The method does a modified semantic version comparison,
    as we want to treat any pre-release as == to the real release
    but in strict semantic versioning it is <
    ie. '8.6.0-pre.m1dev86' is converted to '8.6.0'
    """
    if _current_version is None:
        print("Version is not informed. Returning False")
        return False

    strippedVersion = _current_version.split("-")[0]
    if '.x' in strippedVersion:
        strippedVersion = strippedVersion.replace('.x', '.0')
    current_version = semver.VersionInfo.parse(strippedVersion)
    compareToVersion = semver.VersionInfo.parse(_compare_to_version)
    return current_version.compare(compareToVersion) >= 0
