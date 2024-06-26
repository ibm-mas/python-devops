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

logger = logging.getLogger(__name__)


def connect(server: str, token: str) -> bool:
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
        server=server
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
            tasksCRD = crdAPI.get(name=crdName)
            conditions = tasksCRD.status.conditions
            for condition in conditions:
                if condition.type == "Established":
                    if condition.status == "True":
                        foundReadyCRD = True
                    else:
                        logger.debug("Waiting 5s for tasks.tekton.dev CRD to be ready before checking again ...")
                        sleep(5)
                        continue
        except NotFoundError:
            logger.debug("Waiting 5s for tasks.tekton.dev CRD to be installed before checking again ...")
            sleep(5)
    return foundReadyCRD


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
