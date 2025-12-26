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
from time import sleep

from kubeconfig import KubeConfig
from kubeconfig.exceptions import KubectlNotFoundError
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError

from kubernetes import client
from kubernetes.stream import stream
from kubernetes.stream.ws_client import ERROR_CHANNEL

import yaml

logger = logging.getLogger(__name__)


def connect(server: str, token: str, skipVerify: bool = False) -> bool:
    """
    Connect to a target OpenShift Container Platform (OCP) cluster.

    Configures kubectl/oc context with the provided server URL and authentication token.

    Parameters:
        server (str): The OpenShift cluster API server URL (e.g., "https://api.cluster.example.com:6443")
        token (str): The authentication token for cluster access
        skipVerify (bool, optional): Whether to skip TLS certificate verification. Defaults to False.

    Returns:
        bool: True if connection was successful, False if kubectl is not found on the path

    Raises:
        KubectlNotFoundError: If kubectl/oc is not available in the system PATH
    """
    logger.info(f"Connect(server={server}, token=***)")

    try:
        conf = KubeConfig()
    except KubectlNotFoundError:
        logger.warning("Unable to locate kubectl on the path")
        return False

    conf.view()
    logger.debug(f"Starting KubeConfig context: {conf.current_context()}")

    conf.set_credentials(
        name='my-credentials',
        token=token
    )
    conf.set_cluster(
        name='my-cluster',
        server=server,
        insecure_skip_tls_verify=skipVerify
    )
    conf.set_context(
        name='my-context',
        cluster='my-cluster',
        user='my-credentials'
    )

    conf.use_context('my-context')
    conf.view()
    logger.info(f"KubeConfig context changed to {conf.current_context()}")
    return True


def getClusterVersion(dynClient: DynamicClient) -> str:
    """
    Get the current OpenShift cluster version.

    Retrieves the completed cluster version from the ClusterVersion custom resource.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client

    Returns:
        str: The cluster version string (e.g., "4.12.0"), or None if not found

    Raises:
        NotFoundError: If the ClusterVersion resource cannot be retrieved
    """
    clusterVersionAPI = dynClient.resources.get(api_version="config.openshift.io/v1", kind="ClusterVersion")

    # Version jsonPath = .status.history[?(@.state=="Completed")].version
    try:
        clusterVersion = clusterVersionAPI.get(name="version")
        for record in clusterVersion.status.history:
            if record.state == "Completed":
                return record.version
    except NotFoundError:
        logger.debug("Unable to retrieve ClusterVersion")
    return None


def isClusterVersionInRange(version: str, releases: list[str]) -> bool:
    """
    Check if a cluster version matches any of the specified release versions.

    Parameters:
        version (str): The cluster version to check (e.g., "4.12.0")
        releases (list[str]): List of release version prefixes to match against (e.g., ["4.12", "4.13"])

    Returns:
        bool: True if the version starts with any of the release prefixes, False otherwise
    """
    if releases is not None:
        for release in releases:
            if version.startswith(f"{release}."):
                return True
    return False


def getNamespace(dynClient: DynamicClient, namespace: str) -> dict:
    """
    Get a Kubernetes namespace by name.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The name of the namespace to retrieve

    Returns:
        dict: The namespace resource as a dictionary, or an empty dict if not found

    Raises:
        NotFoundError: If the namespace does not exist
    """
    namespaceAPI = dynClient.resources.get(api_version="v1", kind="Namespace")

    try:
        ns = namespaceAPI.get(name=namespace)
        logger.debug(f"Namespace {namespace} exists")
        return ns
    except NotFoundError:
        logger.debug(f"Namespace {namespace} does not exist")

    return {}


def createNamespace(dynClient: DynamicClient, namespace: str, kyvernoLabel: str = None) -> bool:
    """
    Create a Kubernetes namespace if it does not already exist.

    If the namespace exists and a Kyverno label is provided, the namespace will be patched
    to include the label.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The name of the namespace to create
        kyvernoLabel (str, optional): Value for the 'ibm.com/kyverno' label. Defaults to None.

    Returns:
        bool: Always returns True

    Raises:
        NotFoundError: If the namespace resource cannot be accessed
    """
    namespaceAPI = dynClient.resources.get(api_version="v1", kind="Namespace")
    try:
        ns = namespaceAPI.get(name=namespace)
        logger.info(f"Namespace {namespace} already exists")
        if kyvernoLabel is not None:
            if ns.metadata.labels is None or "ibm.com/kyverno" not in ns.metadata.labels.keys() or ns.metadata.labels["ibm.com/kyverno"] != kyvernoLabel:
                logger.info(f"Patching namespace with Kyverno Labels ibm.com/kyverno: {kyvernoLabel}")
                body = {"metadata": {"labels": {"ibm.com/kyverno": kyvernoLabel}}}
                namespaceAPI.patch(
                    name=namespace,
                    body=body,
                    content_type="application/merge-patch+json"
                )
    except NotFoundError:
        nsObj = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": namespace
            }
        }
        if kyvernoLabel is not None:
            nsObj["metadata"]["labels"] = {
                "ibm.com/kyverno": kyvernoLabel
            }
        namespaceAPI.create(body=nsObj)
        logger.debug(f"Created namespace {namespace}")
    return True


def deleteNamespace(dynClient: DynamicClient, namespace: str) -> bool:
    """
    Delete a Kubernetes namespace if it exists.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The name of the namespace to delete

    Returns:
        bool: Always returns True

    Raises:
        NotFoundError: If the namespace does not exist (caught and logged)
    """
    namespaceAPI = dynClient.resources.get(api_version="v1", kind="Namespace")
    try:
        namespaceAPI.delete(name=namespace)
        logger.debug(f"Namespace {namespace} deleted")
    except NotFoundError:
        logger.debug(f"Namespace {namespace} can not be deleted because it does not exist")
    return True


def waitForCRD(dynClient: DynamicClient, crdName: str) -> bool:
    """
    Wait for a Custom Resource Definition (CRD) to be established and ready.

    Polls the CRD status up to 100 times with 5-second intervals (max ~8 minutes).

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        crdName (str): The name of the CRD to wait for (e.g., "suites.core.mas.ibm.com")

    Returns:
        bool: True if the CRD becomes established, False if timeout is reached

    Raises:
        NotFoundError: If the CRD is not found (caught and retried)
    """
    crdAPI = dynClient.resources.get(api_version="apiextensions.k8s.io/v1", kind="CustomResourceDefinition")
    maxRetries = 100
    foundReadyCRD = False
    retries = 0
    while not foundReadyCRD and retries < maxRetries:
        retries += 1
        try:
            crd = crdAPI.get(name=crdName)
            conditions = crd.status.conditions
            if conditions is None:
                logger.debug(f"Looking for status.conditions to be available to iterate for {crdName}")
                sleep(5)
                continue
            else:
                for condition in conditions:
                    if condition.type == "Established":
                        if condition.status == "True":
                            foundReadyCRD = True
                        else:
                            logger.debug(f"Waiting 5s for {crdName} CRD to be ready before checking again ...")
                            sleep(5)
                            continue
        except NotFoundError:
            logger.debug(f"Waiting 5s for {crdName} CRD to be installed before checking again ...")
            sleep(5)
    return foundReadyCRD


def waitForDeployment(dynClient: DynamicClient, namespace: str, deploymentName: str) -> bool:
    """
    Wait for a Kubernetes Deployment to have at least one ready replica.

    Polls the deployment status up to 100 times with 5-second intervals (max ~8 minutes).

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace containing the deployment
        deploymentName (str): The name of the deployment to wait for

    Returns:
        bool: True if the deployment becomes ready, False if timeout is reached

    Raises:
        NotFoundError: If the deployment is not found (caught and retried)
    """
    deploymentAPI = dynClient.resources.get(api_version="apps/v1", kind="Deployment")
    maxRetries = 100
    foundReadyDeployment = False
    retries = 0
    while not foundReadyDeployment and retries < maxRetries:
        retries += 1
        try:
            deployment = deploymentAPI.get(name=deploymentName, namespace=namespace)
            if deployment.status.readyReplicas is not None and deployment.status.readyReplicas > 0:
                # Depending on how early we are checking the deployment the status subresource may not
                # have even been initialized yet, hence the check for "is not None" to avoid a
                # NoneType and int comparison TypeError
                foundReadyDeployment = True
            else:
                logger.debug(f"Waiting 5s for deployment {deploymentName} to be ready before checking again ...")
                sleep(5)
        except NotFoundError:
            logger.debug(f"Waiting 5s for deployment {deploymentName} to be created before checking again ...")
            sleep(5)
    return foundReadyDeployment


def getConsoleURL(dynClient: DynamicClient) -> str:
    """
    Get the OpenShift web console URL.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client

    Returns:
        str: The HTTPS URL of the OpenShift console (e.g., "https://console-openshift-console.apps.cluster.example.com")

    Raises:
        NotFoundError: If the console route is not found
    """
    routesAPI = dynClient.resources.get(api_version="route.openshift.io/v1", kind="Route")
    consoleRoute = routesAPI.get(name="console", namespace="openshift-console")
    return f"https://{consoleRoute.spec.host}"


def getNodes(dynClient: DynamicClient) -> str:
    """
    Get all nodes in the cluster.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client

    Returns:
        list: List of node resources as dictionaries

    Raises:
        NotFoundError: If nodes cannot be retrieved
    """
    nodesAPI = dynClient.resources.get(api_version="v1", kind="Node")
    nodes = nodesAPI.get().to_dict()['items']
    return nodes


def getStorageClass(dynClient: DynamicClient, name: str) -> str:
    """
    Get a specific StorageClass by name.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        name (str): The name of the StorageClass to retrieve

    Returns:
        StorageClass: The StorageClass resource, or None if not found

    Raises:
        NotFoundError: If the StorageClass does not exist (caught and returns None)
    """
    try:
        storageClassAPI = dynClient.resources.get(api_version="storage.k8s.io/v1", kind="StorageClass")
        storageclass = storageClassAPI.get(name=name)
        return storageclass
    except NotFoundError:
        return None


def getStorageClasses(dynClient: DynamicClient) -> list:
    """
    Get all StorageClasses in the cluster.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client

    Returns:
        list: List of StorageClass resources

    Raises:
        NotFoundError: If StorageClasses cannot be retrieved
    """
    storageClassAPI = dynClient.resources.get(api_version="storage.k8s.io/v1", kind="StorageClass")
    storageClasses = storageClassAPI.get().items
    return storageClasses


def isSNO(dynClient: DynamicClient) -> bool:
    """
    Check if the cluster is a Single Node OpenShift (SNO) deployment.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client

    Returns:
        bool: True if the cluster has exactly one node, False otherwise
    """
    return len(getNodes(dynClient)) == 1


def crdExists(dynClient: DynamicClient, crdName: str) -> bool:
    """
    Check if a Custom Resource Definition (CRD) exists in the cluster.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        crdName (str): The name of the CRD to check (e.g., "suites.core.mas.ibm.com")

    Returns:
        bool: True if the CRD exists, False otherwise

    Raises:
        NotFoundError: If the CRD does not exist (caught and returns False)
    """
    crdAPI = dynClient.resources.get(api_version="apiextensions.k8s.io/v1", kind="CustomResourceDefinition")
    try:
        crdAPI.get(name=crdName)
        logger.debug(f"CRD does exist: {crdName}")
        return True
    except NotFoundError:
        logger.debug(f"CRD does not exist: {crdName}")
        return False


def listInstances(dynClient: DynamicClient, apiVersion: str, kind: str) -> list:
    """
    Get a list of instances of a particular custom resource on the cluster.

    Logs information about each instance found, including name and reconciled version.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        apiVersion (str): The API version of the custom resource (e.g., "core.mas.ibm.com/v1")
        kind (str): The kind of custom resource (e.g., "Suite")

    Returns:
        list: List of custom resource instances as dictionaries

    Raises:
        NotFoundError: If the custom resource type is not found
    """
    api = dynClient.resources.get(api_version=apiVersion, kind=kind)
    instances = api.get().to_dict()['items']
    if len(instances) > 0:
        logger.info(f"There are {len(instances)} {kind} instances installed on this cluster:")
    for instance in instances:
        logger.info(f" * {instance['metadata']['name']} v{instance.get('status', {}).get('versions', {}).get('reconciled', 'N/A')}")
    else:
        logger.info(f"There are no {kind} instances installed on this cluster")
    return instances


def waitForPVC(dynClient: DynamicClient, namespace: str, pvcName: str) -> bool:
    """
    Wait for a PersistentVolumeClaim (PVC) to be bound.

    Allows up to 10 minutes for a PVC to report successful binding, with increasing
    retry delays (30s, then 1m, 2m, and 5m intervals).

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace containing the PVC
        pvcName (str): The name of the PVC to wait for

    Returns:
        bool: True if the PVC becomes bound, False if timeout is reached

    Raises:
        NotFoundError: If the PVC is not found (caught and retried)
    """
    pvcAPI = dynClient.resources.get(api_version="v1", kind="PersistentVolumeClaim")
    maxRetries = 20
    retryDelaySeconds = 30
    foundReadyPVC = False
    retries = 0
    while not foundReadyPVC and retries < maxRetries:
        retries += 1
        # After 5 retries increase the delay to 1 minute
        # After 10 retries increase the delay to 2 minutes
        # After 15 retries increase the delay to 5 minutes
        if retries == 6:
            retryDelaySeconds = 60
        elif retries == 11:
            retryDelaySeconds = 120
        elif retries == 16:
            retryDelaySeconds = 300

        try:
            pvc = pvcAPI.get(name=pvcName, namespace=namespace)
            if pvc.status.phase == "Bound":
                foundReadyPVC = True
            else:
                logger.debug(f"Waiting {retryDelaySeconds}s for PVC {pvcName} to be bound before checking again ...")
                sleep(retryDelaySeconds)
        except NotFoundError:
            logger.debug(f"Waiting {retryDelaySeconds}s for PVC {pvcName} to be created before checking again ...")
            sleep(retryDelaySeconds)

    return foundReadyPVC


# Assisted by WCA@IBM
# Latest GenAI contribution: ibm/granite-8b-code-instruct
def execInPod(core_v1_api: client.CoreV1Api, pod_name: str, namespace, command: list, timeout: int = 60) -> str:
    """
    Executes a command in a Kubernetes pod and returns the standard output.
    If running this function from inside a pod (i.e. config.load_incluster_config()),
    the ServiceAccount assigned to the pod must have the following access in one of the Roles bound to it:
    rules:
      - apiGroups:
          - ""
      resources:
          - pods/exec
      verbs:
          - create
          - get
          - list

    Args:
      core_v1_api (client.CoreV1Api): The Kubernetes API client.
      pod_name (str): The name of the pod to execute the command in.
      namespace (str): The namespace of the pod.
      command (list): The command to execute in the pod.
      timeout (int, optional): The timeout in seconds for the command execution. Defaults to 60.

    Returns:
      str: The standard output of the command.

    Raises:
      Exception: If the command execution fails or times out.
    """
    logger.debug(f"Executing command {command} on pod {pod_name} in {namespace}")
    req = stream(
        core_v1_api.connect_get_namespaced_pod_exec,
        pod_name,
        namespace,
        command=command,
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
        _preload_content=False,
    )
    req.run_forever(timeout)
    stdout = req.read_stdout()
    stderr = req.read_stderr()

    err = yaml.load(req.read_channel(ERROR_CHANNEL), Loader=yaml.FullLoader)
    if err.get("status") == "Failure":
        raise Exception(f"Failed to execute {command} on {pod_name} in namespace {namespace}: {err.get('message')}. stdout: {stdout}, stderr: {stderr}")

    logger.debug(f"stdout: \n----------------------------------------------------------------\n{stdout}\n----------------------------------------------------------------\n")

    return stdout


def updateGlobalPullSecret(dynClient: DynamicClient, registryUrl: str, username: str, password: str) -> dict:
    """
    Update the global pull secret in openshift-config namespace with new registry credentials.

    Args:
        dynClient: OpenShift Dynamic Client
        registryUrl: Registry URL (e.g., "myregistry.com:5000")
        username: Registry username
        password: Registry password

    Returns:
        dict: Updated secret information
    """
    import json
    import base64

    logger.info(f"Updating global pull secret with credentials for {registryUrl}")

    # Get the existing pull secret
    secretsAPI = dynClient.resources.get(api_version="v1", kind="Secret")
    try:
        pullSecret = secretsAPI.get(name="pull-secret", namespace="openshift-config")
    except NotFoundError:
        raise Exception("Global pull-secret not found in openshift-config namespace")

    # Convert to dict to allow modifications
    secretDict = pullSecret.to_dict()

    # Decode the existing dockerconfigjson
    dockerConfigJson = secretDict['data'].get(".dockerconfigjson", "")
    dockerConfig = json.loads(base64.b64decode(dockerConfigJson).decode('utf-8'))

    # Create auth string (username:password base64 encoded)
    authString = base64.b64encode(f"{username}:{password}".encode('utf-8')).decode('utf-8')

    # Add or update the registry credentials
    if "auths" not in dockerConfig:
        dockerConfig["auths"] = {}

    dockerConfig["auths"][registryUrl] = {
        "username": username,
        "password": password,
        "email": username,
        "auth": authString
    }

    # Encode back to base64
    updatedDockerConfig = base64.b64encode(json.dumps(dockerConfig).encode('utf-8')).decode('utf-8')

    # Update the secret dict
    secretDict['data'][".dockerconfigjson"] = updatedDockerConfig

    # Apply the updated secret
    updatedSecret = secretsAPI.apply(body=secretDict, namespace="openshift-config")

    logger.info(f"Successfully updated global pull secret with credentials for {registryUrl}")

    return {
        "name": updatedSecret.metadata.name,
        "namespace": updatedSecret.metadata.namespace,
        "registry": registryUrl,
        "changed": True
    }
