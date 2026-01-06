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
from os import path

from kubernetes.dynamic.exceptions import NotFoundError
from openshift.dynamic import DynamicClient
from jinja2 import Environment, FileSystemLoader

import yaml

from .ocp import createNamespace

logger = logging.getLogger(__name__)


class OLMException(Exception):
    pass


def getPackageManifest(dynClient: DynamicClient, packageName: str, catalogSourceNamespace: str = "openshift-marketplace"):
    """
    Get the PackageManifest for an operator package.

    Retrieves package information including available channels and catalog source.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        packageName (str): Name of the operator package (e.g., "ibm-mas-operator")
        catalogSourceNamespace (str, optional): Namespace containing the catalog source. Defaults to "openshift-marketplace".

    Returns:
        PackageManifest: The package manifest resource, or None if not found

    Raises:
        NotFoundError: If the package manifest is not found (caught and returns None)
    """
    packagemanifestAPI = dynClient.resources.get(api_version="packages.operators.coreos.com/v1", kind="PackageManifest")
    try:
        manifestResource = packagemanifestAPI.get(name=packageName, namespace=catalogSourceNamespace)
        logger.info(f"Package Manifest Details: {catalogSourceNamespace}:{packageName} - Package is available from {manifestResource.status.catalogSource} (default channel is {manifestResource.status.defaultChannel})")
    except NotFoundError:
        logger.info(f"Package Manifest Details: {catalogSourceNamespace}:{packageName} - Package is not available")
        manifestResource = None
    return manifestResource


def ensureOperatorGroupExists(dynClient: DynamicClient, env: Environment, namespace: str, installMode: str = "OwnNamespace"):
    """
    Ensure an OperatorGroup exists in the specified namespace.

    Creates a new OperatorGroup if one doesn't already exist in the namespace.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        env (Environment): Jinja2 environment for template rendering
        namespace (str): The namespace to check/create the OperatorGroup in
        installMode (str, optional): The install mode for the OperatorGroup. Defaults to "OwnNamespace".

    Returns:
        None

    Raises:
        NotFoundError: If resources cannot be accessed
    """
    operatorGroupsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1", kind="OperatorGroup")
    operatorGroupList = operatorGroupsAPI.get(namespace=namespace)
    if len(operatorGroupList.items) == 0:
        logger.debug(f"Creating new OperatorGroup in namespace {namespace}")
        template = env.get_template("operatorgroup.yml.j2")
        renderedTemplate = template.render(
            name="operatorgroup",
            namespace=namespace,
            installMode=installMode
        )
        operatorGroup = yaml.safe_load(renderedTemplate)
        operatorGroupsAPI.apply(body=operatorGroup, namespace=namespace)
    else:
        logger.debug(f"An OperatorGroup already exists in namespace {namespace}")


def getSubscription(dynClient: DynamicClient, namespace: str, packageName: str):
    """
    Get the Subscription for an operator package in a namespace.

    Searches for subscriptions using label selector based on package name and namespace.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to search in
        packageName (str): Name of the operator package

    Returns:
        Subscription: The subscription resource, or None if not found

    Raises:
        NotFoundError: If no subscription is found (returns None)
    """
    labelSelector = f"operators.coreos.com/{packageName}.{namespace}"
    logger.debug(f"Get Subscription for {packageName} in {namespace}")
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")
    subscriptions = subscriptionsAPI.get(label_selector=labelSelector, namespace=namespace)
    if len(subscriptions.items) == 0:
        logger.info(f"No matching Subscription found for {packageName} in {namespace}")
        return None
    elif len(subscriptions.items) > 0:
        logger.warning(f"More than one ({len(subscriptions.items)}) Subscriptions found for {packageName} in {namespace}")
    return subscriptions.items[0]


def applySubscription(dynClient: DynamicClient, namespace: str, packageName: str, packageChannel: str = None, catalogSource: str = None, catalogSourceNamespace: str = "openshift-marketplace", config: dict = None, installMode: str = "OwnNamespace"):
    """
    Create or update an operator subscription in a namespace.

    Automatically detects default channel and catalog source from PackageManifest if not provided.
    Ensures an OperatorGroup exists before creating the subscription.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to create the subscription in
        packageName (str): Name of the operator package (e.g., "ibm-mas-operator")
        packageChannel (str, optional): Subscription channel. Auto-detected if None. Defaults to None.
        catalogSource (str, optional): Catalog source name. Auto-detected if None. Defaults to None.
        catalogSourceNamespace (str, optional): Namespace of the catalog source. Defaults to "openshift-marketplace".
        config (dict, optional): Additional subscription configuration. Defaults to None.
        installMode (str, optional): Install mode for the OperatorGroup. Defaults to "OwnNamespace".

    Returns:
        Subscription: The created or updated subscription resource

    Raises:
        OLMException: If the package is not available in any catalog
        NotFoundError: If resources cannot be created
    """
    if catalogSourceNamespace is None:
        catalogSourceNamespace = "openshift-marketplace"

    labelSelector = f"operators.coreos.com/{packageName}.{namespace}"
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(
        loader=FileSystemLoader(searchpath=templateDir)
    )

    if packageChannel is None or catalogSource is None:
        logger.debug("Getting PackageManifest to determine defaults")
        manifestResource = getPackageManifest(dynClient, packageName, catalogSourceNamespace)
        if manifestResource is None:
            raise OLMException(f"Package {packageName} is not available from any catalog in {catalogSourceNamespace}")

        # Set defaults for optional parameters
        if packageChannel is None:
            logger.debug(f"Setting subscription channel based on PackageManifest: {manifestResource.status.defaultChannel}")
            packageChannel = manifestResource.status.defaultChannel
        if catalogSource is None:
            logger.debug(f"Setting subscription catalogSource based on PackageManifest: {manifestResource.status.catalogSource}")
            catalogSource = manifestResource.status.catalogSource

    # Create the Namespace & OperatorGroup if necessary
    logger.debug(f"Setting up OperatorGroup in {namespace}")
    createNamespace(dynClient, namespace)
    ensureOperatorGroupExists(dynClient, env, namespace, installMode)

    # Create (or update) the subscription
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")

    resources = subscriptionsAPI.get(label_selector=labelSelector, namespace=namespace)
    if len(resources.items) == 0:
        name = packageName
        logger.info(f"Creating new subscription {name} in {namespace}")
    elif len(resources.items) == 1:
        name = resources.items[0].metadata.name
        logger.info(f"Updating existing subscription {name} in {namespace}")
    else:
        raise OLMException(f"More than one subscription found in {namespace} for {packageName} ({len(resources.items)} subscriptions found)")

    template = env.get_template("subscription.yml.j2")
    renderedTemplate = template.render(
        subscription_name=name,
        subscription_namespace=namespace,
        subscription_config=config,
        package_name=packageName,
        package_channel=packageChannel,
        catalog_name=catalogSource,
        catalog_namespace=catalogSourceNamespace
    )
    subscription = yaml.safe_load(renderedTemplate)
    subscriptionsAPI.apply(body=subscription, namespace=namespace)

    # Wait for InstallPlan to be created
    logger.debug(f"Waiting for {packageName}.{namespace} InstallPlans")
    installPlanAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="InstallPlan")

    installPlanResources = installPlanAPI.get(label_selector=labelSelector, namespace=namespace)
    while len(installPlanResources.items) == 0:
        installPlanResources = installPlanAPI.get(label_selector=labelSelector, namespace=namespace)
        sleep(30)

    if len(installPlanResources.items) == 0:
        raise OLMException(f"Found 0 InstallPlans for {packageName}")
    elif len(installPlanResources.items) > 1:
        logger.warning(f"More than 1 InstallPlan found for {packageName}")
    else:
        installPlanName = installPlanResources.items[0].metadata.name

    # Wait for InstallPlan to complete
    logger.debug(f"Waiting for InstallPlan {installPlanName}")
    installPlanPhase = installPlanResources.items[0].status.phase
    while installPlanPhase != "Complete":
        installPlanResource = installPlanAPI.get(name=installPlanName, namespace=namespace)
        installPlanPhase = installPlanResource.status.phase
        sleep(30)

    # Wait for Subscription to complete
    logger.debug(f"Waiting for Subscription {name} in {namespace}")
    while True:
        subscriptionResource = subscriptionsAPI.get(name=name, namespace=namespace)
        state = getattr(subscriptionResource.status, "state", None)

        if state == "AtLatestKnown":
            logger.debug(f"Subscription {name} in {namespace} reached state: {state}")
            return subscriptionResource

        logger.debug(f"Subscription {name} in {namespace} not ready yet (state = {state}), retrying...")
        sleep(30)


def deleteSubscription(dynClient: DynamicClient, namespace: str, packageName: str) -> None:
    labelSelector = f"operators.coreos.com/{packageName}.{namespace}"

    # Find and delete the Subscription
    logger.debug(f"Deleting Subscription for {packageName} in {namespace}")
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")
    _findAndDeleteResources(subscriptionsAPI, "Subscription", labelSelector, namespace)

    # Find and delete the CSV
    logger.debug(f"Deleting CSV for {packageName}")
    csvAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="ClusterServiceVersion")
    _findAndDeleteResources(csvAPI, "CSV", labelSelector, namespace)


def _findAndDeleteResources(api, resourceType: str, labelSelector: str, namespace: str):
    resources = api.get(label_selector=labelSelector, namespace=namespace)
    if len(resources.items) == 0:
        logger.info(f"No matching {resourceType}s to delete")
    else:
        for item in resources.items:
            logger.info(f"Deleting {resourceType} {item.metadata.name}")
            api.delete(name=item.metadata.name, namespace=namespace)
