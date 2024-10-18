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
    Connect to target OCP
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


def createNamespace(dynClient: DynamicClient, namespace: str) -> bool:
    """
    Create a namespace if it does not exist
    """
    namespaceAPI = dynClient.resources.get(api_version="v1", kind="Namespace")
    try:
        namespaceAPI.get(name=namespace)
        logger.debug(f"Namespace {namespace} already exists")
    except NotFoundError:
        nsObj = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": namespace
            }
        }
        namespaceAPI.create(body=nsObj)
        logger.debug(f"Created namespace {namespace}")
    return True


def waitForCRD(dynClient: DynamicClient, crdName: str) -> bool:
    crdAPI = dynClient.resources.get(api_version="apiextensions.k8s.io/v1", kind="CustomResourceDefinition")
    maxRetries = 100
    foundReadyCRD = False
    retries = 0
    while not foundReadyCRD and retries < maxRetries:
        retries += 1
        try:
            crd = crdAPI.get(name=crdName)
            conditions = crd.status.conditions
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
                logger.debug("Waiting 5s for deployment {deploymentName} to be ready before checking again ...")
                sleep(5)
        except NotFoundError:
            logger.debug("Waiting 5s for deployment {deploymentName} to be created before checking again ...")
            sleep(5)
    return foundReadyDeployment


def getConsoleURL(dynClient: DynamicClient) -> str:
    routesAPI = dynClient.resources.get(api_version="route.openshift.io/v1", kind="Route")
    consoleRoute = routesAPI.get(name="console", namespace="openshift-console")
    return f"https://{consoleRoute.spec.host}"


def getNodes(dynClient: DynamicClient) -> str:
    try:
        nodesAPI = dynClient.resources.get(api_version="v1", kind="Node")
        nodes = nodesAPI.get().to_dict()['items']
        return nodes
    except Exception as e:
        logger.error(f"Error: Unable to get nodes: {e}")
        return []


def getStorageClass(dynClient: DynamicClient, name: str) -> str:
    try:
        storageClassAPI = dynClient.resources.get(api_version="storage.k8s.io/v1", kind="StorageClass")
        storageclass = storageClassAPI.get(name=name)
        return storageclass
    except NotFoundError:
        return None


def getStorageClasses(dynClient: DynamicClient) -> list:
    storageClassAPI = dynClient.resources.get(api_version="storage.k8s.io/v1", kind="StorageClass")
    storageClasses = storageClassAPI.get().items
    return storageClasses


def isSNO(dynClient: DynamicClient) -> bool:
    return len(getNodes(dynClient)) == 1


def crdExists(dynClient: DynamicClient, crdName: str) -> bool:
    crdAPI = dynClient.resources.get(api_version="apiextensions.k8s.io/v1", kind="CustomResourceDefinition")
    try:
        crdAPI.get(name=crdName)
        logger.debug(f"CRD does exist: {crdName}")
        return True
    except NotFoundError:
        logger.debug(f"CRD does not exist: {crdName}")
        return False

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
