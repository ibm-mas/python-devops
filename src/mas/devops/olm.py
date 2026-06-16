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
from typing import Optional

from kubernetes.dynamic.exceptions import NotFoundError
from openshift.dynamic import DynamicClient
from jinja2 import Environment, FileSystemLoader

import yaml

from .ocp import createNamespace

logger = logging.getLogger(__name__)


class OLMException(Exception):
    pass


def getPackageManifest(
    dynClient: DynamicClient,
    packageName: str,
    catalogSourceNamespace: str = "openshift-marketplace",
):
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
    packagemanifestAPI = dynClient.resources.get(
        api_version="packages.operators.coreos.com/v1", kind="PackageManifest"
    )
    try:
        manifestResource = packagemanifestAPI.get(
            name=packageName, namespace=catalogSourceNamespace
        )
        logger.info(
            f"Package Manifest Details: {catalogSourceNamespace}:{packageName} - Package is available from {manifestResource.status.catalogSource} (default channel is {manifestResource.status.defaultChannel})"
        )
    except NotFoundError:
        logger.info(
            f"Package Manifest Details: {catalogSourceNamespace}:{packageName} - Package is not available"
        )
        manifestResource = None
    return manifestResource


def ensureOperatorGroupExists(
    dynClient: DynamicClient,
    env: Environment,
    namespace: str,
    installMode: str = "OwnNamespace",
):
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
    operatorGroupsAPI = dynClient.resources.get(
        api_version="operators.coreos.com/v1", kind="OperatorGroup"
    )
    operatorGroupList = operatorGroupsAPI.get(namespace=namespace)
    if len(operatorGroupList.items) == 0:
        logger.debug(f"Creating new OperatorGroup in namespace {namespace}")
        template = env.get_template("operatorgroup.yml.j2")
        renderedTemplate = template.render(
            name="operatorgroup", namespace=namespace, installMode=installMode
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
    subscriptionsAPI = dynClient.resources.get(
        api_version="operators.coreos.com/v1alpha1", kind="Subscription"
    )
    subscriptions = subscriptionsAPI.get(
        label_selector=labelSelector, namespace=namespace
    )
    if len(subscriptions.items) == 0:
        logger.info(f"No matching Subscription found for {packageName} in {namespace}")
        return None
    elif len(subscriptions.items) > 0:
        logger.warning(
            f"More than one ({len(subscriptions.items)}) Subscriptions found for {packageName} in {namespace}"
        )
    return subscriptions.items[0]


def applySubscription(
    dynClient: DynamicClient,
    namespace: str,
    packageName: str,
    packageChannel: Optional[str] = None,
    catalogSource: Optional[str] = None,
    catalogSourceNamespace: str = "openshift-marketplace",
    config: Optional[dict] = None,
    installMode: str = "OwnNamespace",
    installPlanApproval: Optional[str] = None,
    startingCSV: Optional[str] = None,
):
    """
    Create or update an operator subscription in a namespace.

    Automatically detects default channel and catalog source from PackageManifest if not provided.
    Ensures an OperatorGroup exists before creating the subscription.

    When installPlanApproval is set to "Manual" and a startingCSV is specified, this function will
    automatically approve the InstallPlan for the first-time installation to move to that startingCSV.
    Subsequent upgrades will still require manual approval.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to create the subscription in
        packageName (str): Name of the operator package (e.g., "ibm-mas-operator")
        packageChannel (str, optional): Subscription channel. Auto-detected if None. Defaults to None.
        catalogSource (str, optional): Catalog source name. Auto-detected if None. Defaults to None.
        catalogSourceNamespace (str, optional): Namespace of the catalog source. Defaults to "openshift-marketplace".
        config (dict, optional): Additional subscription configuration. Defaults to None.
        installMode (str, optional): Install mode for the OperatorGroup. Defaults to "OwnNamespace".
        installPlanApproval (str, optional): Install plan approval mode ("Automatic" or "Manual"). Defaults to None.
        startingCSV (str, optional): The specific CSV version to install. When combined with Manual approval,
            the first InstallPlan to this CSV will be automatically approved. Required when installPlanApproval is "Manual". Defaults to None.

    Returns:
        Subscription: The created or updated subscription resource

    Raises:
        OLMException: If the package is not available in any catalog, or if installPlanApproval is "Manual" without a startingCSV
        NotFoundError: If resources cannot be created
    """
    # Validate that startingCSV is provided when installPlanApproval is Manual
    if installPlanApproval == "Manual" and startingCSV is None:
        raise OLMException(
            "When installPlanApproval is 'Manual', a startingCSV must be provided"
        )
    if catalogSourceNamespace is None:
        catalogSourceNamespace = "openshift-marketplace"

    labelSelector = f"operators.coreos.com/{packageName}.{namespace}"
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(loader=FileSystemLoader(searchpath=templateDir))

    if packageChannel is None or catalogSource is None:
        logger.debug("Getting PackageManifest to determine defaults")
        manifestResource = getPackageManifest(
            dynClient, packageName, catalogSourceNamespace
        )
        if manifestResource is None:
            raise OLMException(
                f"Package {packageName} is not available from any catalog in {catalogSourceNamespace}"
            )

        # Set defaults for optional parameters
        if packageChannel is None:
            logger.debug(
                f"Setting subscription channel based on PackageManifest: {manifestResource.status.defaultChannel}"
            )
            packageChannel = manifestResource.status.defaultChannel
        if catalogSource is None:
            logger.debug(
                f"Setting subscription catalogSource based on PackageManifest: {manifestResource.status.catalogSource}"
            )
            catalogSource = manifestResource.status.catalogSource

    # Create the Namespace & OperatorGroup if necessary
    logger.debug(f"Setting up OperatorGroup in {namespace}")
    createNamespace(dynClient, namespace)
    ensureOperatorGroupExists(dynClient, env, namespace, installMode)

    # Create (or update) the subscription
    subscriptionsAPI = dynClient.resources.get(
        api_version="operators.coreos.com/v1alpha1", kind="Subscription"
    )

    resources = subscriptionsAPI.get(label_selector=labelSelector, namespace=namespace)
    if len(resources.items) == 0:
        name = packageName
        logger.info(f"Creating new subscription {name} in {namespace}")
    elif len(resources.items) == 1:
        name = resources.items[0].metadata.name
        logger.info(f"Updating existing subscription {name} in {namespace}")
    else:
        raise OLMException(
            f"More than one subscription found in {namespace} for {packageName} ({len(resources.items)} subscriptions found)"
        )

    template = env.get_template("subscription.yml.j2")
    renderedTemplate = template.render(
        subscription_name=name,
        subscription_namespace=namespace,
        subscription_config=config,
        package_name=packageName,
        package_channel=packageChannel,
        catalog_name=catalogSource,
        catalog_namespace=catalogSourceNamespace,
        install_plan_approval=installPlanApproval,
        starting_csv=startingCSV,
    )
    subscription = yaml.safe_load(renderedTemplate)

    # apply should work regardless of if the subscription already exists or not,
    # however if two parallel processes call it at the same time it can result
    # in a 409 error in that case trying again will resolve the issue
    try:
        subscriptionsAPI.apply(body=subscription, namespace=namespace)
    except Exception as e:
        if "409" in str(e) or "AlreadyExists" in str(e):
            logger.warning(
                f"Subscription {name} already exists and produced a conflict, retrying the apply"
            )
            subscriptionsAPI.apply(body=subscription, namespace=namespace)
        else:
            raise

    # Wait for InstallPlan to be created
    logger.debug(f"Waiting for {packageName}.{namespace} InstallPlans")
    installPlanAPI = dynClient.resources.get(
        api_version="operators.coreos.com/v1alpha1", kind="InstallPlan"
    )

    # Use label selector to get InstallPlans (standard approach)
    installPlanResources = installPlanAPI.get(
        label_selector=labelSelector, namespace=namespace
    )
    while len(installPlanResources.items) == 0:
        installPlanResources = installPlanAPI.get(
            label_selector=labelSelector, namespace=namespace
        )
        sleep(30)

    if len(installPlanResources.items) == 0:
        raise OLMException(f"Found 0 InstallPlans for {packageName}")
    elif len(installPlanResources.items) > 1:
        logger.warning(
            f"More than 1 InstallPlan found for {packageName} using label selector"
        )

    # Select the InstallPlan to use
    installPlanResource = None

    # Special handling for Manual approval with startingCSV
    if installPlanApproval == "Manual" and startingCSV is not None:
        logger.debug(
            f"Manual approval with startingCSV {startingCSV} - checking if label selector returned correct InstallPlan"
        )

        # Check if any of the InstallPlans from label selector match the startingCSV
        for plan in installPlanResources.items:
            csvNames = getattr(plan.spec, "clusterServiceVersionNames", [])
            logger.debug(
                f"InstallPlan {plan.metadata.name} (from label selector) contains CSVs: {csvNames}"
            )
            if csvNames and startingCSV in csvNames:
                installPlanResource = plan
                logger.info(
                    f"Found InstallPlan {plan.metadata.name} matching startingCSV {startingCSV} via label selector"
                )
                break

        # If no match found via label selector, search all InstallPlans owned by this subscription
        if installPlanResource is None:
            logger.warning(
                f"Label selector did not return InstallPlan matching startingCSV {startingCSV}"
            )
            logger.debug(
                f"Searching all InstallPlans in {namespace} owned by subscription {name}"
            )

            allInstallPlans = installPlanAPI.get(namespace=namespace)
            for plan in allInstallPlans.items:
                # Check if this InstallPlan is owned by our subscription
                owner_refs = getattr(plan.metadata, "ownerReferences", [])
                is_owned_by_subscription = any(
                    ref.kind == "Subscription" and ref.name == name
                    for ref in owner_refs
                )

                if is_owned_by_subscription:
                    csvNames = getattr(plan.spec, "clusterServiceVersionNames", [])
                    logger.debug(
                        f"InstallPlan {plan.metadata.name} (owned by subscription) contains CSVs: {csvNames}"
                    )
                    if csvNames and startingCSV in csvNames:
                        installPlanResource = plan
                        logger.info(
                            f"Found InstallPlan {plan.metadata.name} matching startingCSV {startingCSV} via subscription ownership"
                        )
                        break

            if installPlanResource is None:
                logger.warning(
                    f"No InstallPlan found matching startingCSV {startingCSV}, using first from label selector"
                )
                installPlanResource = installPlanResources.items[0]
    else:
        # Standard case: use first InstallPlan from label selector
        installPlanResource = installPlanResources.items[0]

    installPlanName = installPlanResource.metadata.name
    installPlanPhase = installPlanResource.status.phase

    # If the InstallPlan for our startingCSV is already Complete, we're done
    if installPlanPhase == "Complete":
        logger.info(
            f"InstallPlan {installPlanName} for {startingCSV} is already Complete"
        )
    else:
        # Wait for InstallPlan to complete
        logger.debug(f"Waiting for InstallPlan {installPlanName}")

        # Track if we've already approved this install plan
        approved_manual_install = False

        while installPlanPhase != "Complete":
            installPlanResource = installPlanAPI.get(
                name=installPlanName, namespace=namespace
            )
            installPlanPhase = installPlanResource.status.phase

            # If InstallPlan requires approval and this is the first installation to startingCSV
            if installPlanPhase == "RequiresApproval" and not approved_manual_install:
                # Check if this is the first installation by verifying the CSV matches startingCSV
                if startingCSV is not None:
                    csvName = getattr(
                        installPlanResource.spec, "clusterServiceVersionNames", []
                    )
                    if csvName and startingCSV in csvName:
                        logger.info(
                            f"Approving InstallPlan {installPlanName} for first-time installation to {startingCSV}"
                        )
                        # Patch the InstallPlan to approve it
                        installPlanResource.spec.approved = True
                        installPlanAPI.patch(
                            body=installPlanResource,
                            name=installPlanName,
                            namespace=namespace,
                            content_type="application/merge-patch+json",
                        )
                        approved_manual_install = True
                        logger.info(
                            f"InstallPlan {installPlanName} approved successfully"
                        )
                    else:
                        logger.debug(
                            f"InstallPlan CSV {csvName} does not match startingCSV {startingCSV}, waiting for manual approval"
                        )
                else:
                    logger.debug(
                        f"No startingCSV specified, InstallPlan {installPlanName} requires manual approval"
                    )

            sleep(30)

    # Wait for Subscription to complete
    logger.debug(f"Waiting for Subscription {name} in {namespace}")
    while True:
        subscriptionResource = subscriptionsAPI.get(name=name, namespace=namespace)
        state = getattr(subscriptionResource.status, "state", None)

        # When manual approval is used with startingCSV, the state will be "UpgradePending"
        # after the initial installation completes (indicating newer versions are available
        # but require manual approval). For automatic approval, the state will be "AtLatestKnown".
        if state == "AtLatestKnown":
            logger.debug(f"Subscription {name} in {namespace} reached state: {state}")
            return subscriptionResource
        elif (
            state == "UpgradePending"
            and installPlanApproval == "Manual"
            and startingCSV is not None
        ):
            # Verify the installed CSV matches the startingCSV
            installedCSV = getattr(subscriptionResource.status, "installedCSV", None)
            if installedCSV == startingCSV:
                logger.debug(
                    f"Subscription {name} in {namespace} reached state: {state} with installedCSV: {installedCSV}"
                )
                return subscriptionResource
            else:
                logger.debug(
                    f"Subscription {name} in {namespace} state is {state} but installedCSV ({installedCSV}) does not match startingCSV ({startingCSV}), retrying..."
                )

        logger.debug(
            f"Subscription {name} in {namespace} not ready yet (state = {state}), retrying..."
        )
        sleep(30)


def deleteSubscription(
    dynClient: DynamicClient, namespace: str, packageName: str
) -> None:
    labelSelector = f"operators.coreos.com/{packageName}.{namespace}"

    # Find and delete the Subscription
    logger.debug(f"Deleting Subscription for {packageName} in {namespace}")
    subscriptionsAPI = dynClient.resources.get(
        api_version="operators.coreos.com/v1alpha1", kind="Subscription"
    )
    _findAndDeleteResources(subscriptionsAPI, "Subscription", labelSelector, namespace)

    # Find and delete the CSV
    logger.debug(f"Deleting CSV for {packageName}")
    csvAPI = dynClient.resources.get(
        api_version="operators.coreos.com/v1alpha1", kind="ClusterServiceVersion"
    )
    _findAndDeleteResources(csvAPI, "CSV", labelSelector, namespace)


def _findAndDeleteResources(api, resourceType: str, labelSelector: str, namespace: str):
    resources = api.get(label_selector=labelSelector, namespace=namespace)
    if len(resources.items) == 0:
        logger.info(f"No matching {resourceType}s to delete")
    else:
        for item in resources.items:
            logger.info(f"Deleting {resourceType} {item.metadata.name}")
            api.delete(name=item.metadata.name, namespace=namespace)
