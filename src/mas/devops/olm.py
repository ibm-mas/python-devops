# *****************************************************************************
# Copyright (c) 2024, 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

"""
Operator Lifecycle Manager (OLM) utilities.

Provides functions to create and manage operator subscriptions and install
plans, including support for manual install plan approval workflows.
"""

import logging
from time import sleep, time
from os import path
from typing import Callable, Optional, Union

from jinja2 import Environment, FileSystemLoader
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import NotFoundError

import yaml

from .ocp import applyResource, createNamespace

logger = logging.getLogger(__name__)


class OLMException(Exception):
    pass


class OLMTimeoutError(OLMException):
    """Raised when a wait-style OLM function exceeds its configured timeout.

    Subclass of OLMException so that existing `except OLMException` handlers
    continue to catch timeout failures.
    """

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
    packagemanifestAPI = dynClient.resources.get(api_version="packages.operators.coreos.com/v1", kind="PackageManifest")
    try:
        manifestResource = packagemanifestAPI.get(name=packageName, namespace=catalogSourceNamespace)
        logger.info(
            f"Package Manifest Details: {catalogSourceNamespace}:{packageName} - Package is available from {manifestResource.status.catalogSource} (default channel is {manifestResource.status.defaultChannel})"
        )
    except NotFoundError:
        logger.info(f"Package Manifest Details: {catalogSourceNamespace}:{packageName} - Package is not available")
        manifestResource = None
    return manifestResource


def _channelHeadFromManifest(manifest, channel: Optional[str]) -> Optional[str]:
    """The currentCSV of one channel entry in a PackageManifest.

    Shared by getChannelHeadCSV (one-off lookups) and the convergence
    snapshot (poll loop, via the cached manifest fetch). Returns None when
    the manifest is absent or does not carry the named channel.
    """
    if manifest is None:
        return None
    for channelEntry in getattr(manifest.status, "channels", None) or []:
        if getattr(channelEntry, "name", None) == channel:
            return getattr(channelEntry, "currentCSV", None)
    return None


def getChannelHeadCSV(
    dynClient: DynamicClient,
    packageName: str,
    channel: str,
    catalogSourceNamespace: str = "openshift-marketplace",
) -> Optional[str]:
    """
    Get the head CSV of a channel from an operator's PackageManifest.

    The channel head is the deterministic target a Subscription on that
    channel converges to: OLM resolves the Subscription against the catalog
    and promotes status.installedCSV to this CSV once the corresponding
    InstallPlan has been approved (by a human under Manual approval, or by
    OLM itself under Automatic) and has completed.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        packageName (str): Name of the operator package (e.g., "ibm-mas-operator")
        channel (str): The channel to resolve (e.g., "8.x")
        catalogSourceNamespace (str, optional): Namespace containing the catalog source. Defaults to "openshift-marketplace".

    Returns:
        str: The currentCSV of the channel (e.g., "ibm-mas-operator.v9.0.0"),
            or None when the PackageManifest or the channel entry is absent
    """
    manifest = getPackageManifest(dynClient, packageName, catalogSourceNamespace)
    return _channelHeadFromManifest(manifest, channel)


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
    operatorGroupsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1", kind="OperatorGroup")
    operatorGroupList = operatorGroupsAPI.get(namespace=namespace)
    if len(operatorGroupList.items) == 0:
        logger.debug(f"Creating new OperatorGroup in namespace {namespace}")
        template = env.get_template("operatorgroup.yml.j2")
        renderedTemplate = template.render(name="operatorgroup", namespace=namespace, installMode=installMode)
        operatorGroup = yaml.safe_load(renderedTemplate)
        applyResource(
            dynClient=dynClient,
            apiVersion="operators.coreos.com/v1",
            kind="OperatorGroup",
            body=operatorGroup,
            namespace=namespace,
        )
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


def getSubscriptionApprovalMode(dynClient: DynamicClient, namespace: str) -> Optional[str]:
    """Get the effective install plan approval mode for a namespace.

    Although installPlanApproval is stored on each Subscription, this library treats
    approval mode as a namespace property: InstallPlans are namespace-scoped and the
    pause/awareness semantics built on top of this function are namespace-oriented.
    Note that OLM itself does not enforce this, and will automatically create
    dependency Subscriptions (which may default to Automatic) in the same namespace.

    A namespace whose Subscriptions use a mix of approval modes is reported as
    "Mixed": OLM permits per-Subscription modes and auto-creates dependency
    Subscriptions that can legitimately introduce a mix. For waiting semantics a
    Mixed namespace behaves the same as Manual -- InstallPlans in RequiresApproval
    gate processing regardless of which Subscription generated them.

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to inspect

    Returns:
        str: The namespace's approval mode ("Automatic", "Manual" or "Mixed"), or
            None when the namespace contains no Subscriptions
    """
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")
    try:
        subscriptions = subscriptionsAPI.get(namespace=namespace)
    except NotFoundError:
        return None

    modes = {}
    for subscription in subscriptions.items:
        mode = getattr(subscription.spec, "installPlanApproval", None) or "Automatic"
        modes.setdefault(mode, []).append(subscription.metadata.name)

    if len(modes) == 0:
        logger.debug(f"No subscriptions found in namespace {namespace}")
        return None
    elif len(modes) > 1:
        conflicts = ", ".join(f"{name} ({mode})" for mode, names in modes.items() for name in names)
        logger.warning(f"Mixed install plan approval modes in namespace {namespace}: {conflicts}")
        return "Mixed"

    return next(iter(modes))


def getClusterApprovalMode(dynClient: DynamicClient, namespacePrefix: Optional[str] = None) -> dict:
    """Aggregate the effective install plan approval mode across a scope.

    The approval mode was chosen at install time and is a property of the
    cluster, so commands that re-apply or roll subscriptions (update, upgrade)
    detect it rather than ask for it. This function aggregates the effective
    mode (spec.installPlanApproval, unset = "Automatic") of every Subscription
    in scope: cluster-wide when no prefix is given (the update blast radius),
    or restricted to namespaces whose name starts with namespacePrefix (the
    upgrade blast radius, e.g. "mas-inst1-").

    A scope containing both modes is reported as "Mixed": consistent with the
    namespace-level semantics, Mixed behaves the same as Manual for waiting
    purposes (the caller decides how to act on the aggregate).

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespacePrefix (str, optional): Restrict the scope to namespaces whose
            name starts with this prefix. None inspects the whole cluster.
            Defaults to None.

    Returns:
        dict: Cluster approval status with keys approvalMode ("Automatic",
            "Manual", "Mixed", or None when no Subscriptions are in scope),
            counts (dict mapping each mode found to the number of
            Subscriptions using it), namespaces (sorted list of the namespaces
            inspected) and subscriptions (int, total Subscriptions in scope)
    """
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")
    subscriptions = list(subscriptionsAPI.get().items)

    if namespacePrefix is not None:
        subscriptions = [subscription for subscription in subscriptions if subscription.metadata.namespace.startswith(namespacePrefix)]

    modes = {}
    namespaces = set()
    for subscription in subscriptions:
        mode = getattr(subscription.spec, "installPlanApproval", None) or "Automatic"
        modes.setdefault(mode, []).append(subscription.metadata.name)
        namespaces.add(subscription.metadata.namespace)

    if len(modes) == 0:
        approvalMode = None
    elif len(modes) == 1:
        approvalMode = next(iter(modes))
    else:
        approvalMode = "Mixed"

    return {
        "approvalMode": approvalMode,
        "counts": {mode: len(names) for mode, names in modes.items()},
        "namespaces": sorted(namespaces),
        "subscriptions": len(subscriptions),
    }


def _describePendingInstallPlan(installPlanResource, subscriptions: list) -> dict:
    """Build the normalized approval info dict for a pending InstallPlan.

    The owning Subscription is resolved via ownerReferences first, falling back to
    the OLM label (operators.coreos.com/<package>.<namespace>) that InstallPlans
    inherit from their Subscription.

    Args:
        installPlanResource (InstallPlan): The InstallPlan resource to describe
        subscriptions (list): Subscription resources in the same namespace, used to
            resolve the owning Subscription

    Returns:
        dict: Approval info with keys installPlan, namespace, subscription, package,
            csvNames, currentCSV, targetCSV and created
    """
    namespace = installPlanResource.metadata.namespace
    subscriptionResource = None

    # Resolve the owning Subscription via ownerReferences first
    for ownerRef in getattr(installPlanResource.metadata, "ownerReferences", None) or []:
        if ownerRef.kind == "Subscription":
            for subscription in subscriptions:
                if subscription.metadata.name == ownerRef.name:
                    subscriptionResource = subscription
                    break
            if subscriptionResource is not None:
                break

    # Fall back to the OLM label that InstallPlans inherit from their Subscription
    packageName = None
    if subscriptionResource is None:
        labels = getattr(installPlanResource.metadata, "labels", None) or {}
        for labelKey in labels:
            if labelKey.startswith("operators.coreos.com/"):
                suffix = labelKey.split("/", 1)[1]
                if suffix.endswith(f".{namespace}") and len(suffix) > len(namespace) + 1:
                    packageName = suffix[: -(len(namespace) + 1)]
                break

        if packageName is not None:
            for subscription in subscriptions:
                if getattr(subscription.spec, "name", None) == packageName:
                    subscriptionResource = subscription
                    break

    if subscriptionResource is not None:
        packageName = getattr(subscriptionResource.spec, "name", None)
        subscriptionName = subscriptionResource.metadata.name
        currentCSV = getattr(subscriptionResource.status, "installedCSV", None)
    else:
        subscriptionName = None
        currentCSV = None

    csvNames = list(getattr(installPlanResource.spec, "clusterServiceVersionNames", None) or [])
    created = getattr(installPlanResource.metadata, "creationTimestamp", None)

    return {
        "installPlan": installPlanResource.metadata.name,
        "namespace": namespace,
        "subscription": subscriptionName,
        "package": packageName,
        "csvNames": csvNames,
        "currentCSV": currentCSV,
        "targetCSV": csvNames[-1] if csvNames else None,
        "created": str(created) if created is not None else None,
    }


def getPendingInstallPlans(dynClient: DynamicClient, namespace: Optional[str] = None) -> list:
    """List InstallPlans awaiting approval.

    InstallPlans in phase RequiresApproval are returned as normalized approval info
    dicts, enriched with the owning Subscription resolved via ownerReferences or the
    OLM label. This is the data source for approval guidance interfaces.

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str, optional): Restrict the search to a single namespace. When
            None, all namespaces are searched. Defaults to None.

    Returns:
        list: Approval info dicts as produced by the internal describe helper; empty
            list when nothing is awaiting approval
    """
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")
    installPlanAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="InstallPlan")

    if namespace is not None:
        installPlanResources = installPlanAPI.get(namespace=namespace)
    else:
        installPlanResources = installPlanAPI.get()

    # Cache the Subscription list per namespace so each namespace is queried at most once
    subscriptionsByNamespace = {}

    pendingApprovals = []
    for installPlanResource in installPlanResources.items:
        if getattr(installPlanResource.status, "phase", None) != "RequiresApproval":
            continue

        installPlanNamespace = installPlanResource.metadata.namespace
        if installPlanNamespace not in subscriptionsByNamespace:
            try:
                subscriptionList = subscriptionsAPI.get(namespace=installPlanNamespace)
                subscriptionsByNamespace[installPlanNamespace] = list(subscriptionList.items)
            except NotFoundError:
                subscriptionsByNamespace[installPlanNamespace] = []

        pendingApprovals.append(_describePendingInstallPlan(installPlanResource, subscriptionsByNamespace[installPlanNamespace]))

    return pendingApprovals


def getPendingInstallPlan(dynClient: DynamicClient, namespace: str, packageName: str) -> Optional[dict]:
    """Get the InstallPlan awaiting approval for a subscription.

    Searches for an InstallPlan in phase RequiresApproval belonging to the
    Subscription for packageName, using the OLM label selector first and falling
    back to subscription ownership of all InstallPlans in the namespace.

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to search in
        packageName (str): Name of the operator package

    Returns:
        dict: Approval info for the pending InstallPlan, or None when the
            Subscription does not exist or has no InstallPlan awaiting approval
    """
    subscriptionResource = getSubscription(dynClient, namespace, packageName)
    if subscriptionResource is None:
        return None

    installPlanAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="InstallPlan")
    labelSelector = f"operators.coreos.com/{packageName}.{namespace}"

    # Look for a pending InstallPlan via the label inherited from the Subscription first
    installPlanResources = installPlanAPI.get(label_selector=labelSelector, namespace=namespace)
    for installPlanResource in installPlanResources.items:
        if getattr(installPlanResource.status, "phase", None) == "RequiresApproval":
            return _describePendingInstallPlan(installPlanResource, [subscriptionResource])

    # Fall back to searching all InstallPlans in the namespace for one owned by the Subscription
    allInstallPlans = installPlanAPI.get(namespace=namespace)
    for installPlanResource in allInstallPlans.items:
        ownerRefs = getattr(installPlanResource.metadata, "ownerReferences", None) or []
        isOwnedBySubscription = any(ref.kind == "Subscription" and ref.name == subscriptionResource.metadata.name for ref in ownerRefs)
        if isOwnedBySubscription and getattr(installPlanResource.status, "phase", None) == "RequiresApproval":
            return _describePendingInstallPlan(installPlanResource, [subscriptionResource])

    return None


def approveInstallPlan(dynClient: DynamicClient, namespace: str, installPlanName: str):
    """Approve an InstallPlan.

    Patches spec.approved to true using a merge patch. The operation is
    idempotent: an InstallPlan that is already approved or already Complete is
    left untouched.

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace containing the InstallPlan
        installPlanName (str): Name of the InstallPlan to approve

    Returns:
        InstallPlan: The approved (or already-approved) InstallPlan resource

    Raises:
        OLMException: If the InstallPlan has failed and can no longer be approved
        NotFoundError: If the InstallPlan does not exist
    """
    installPlanAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="InstallPlan")
    installPlanResource = installPlanAPI.get(name=installPlanName, namespace=namespace)
    installPlanPhase = getattr(installPlanResource.status, "phase", None)

    if getattr(installPlanResource.spec, "approved", False) or installPlanPhase == "Complete":
        logger.info(f"InstallPlan {installPlanName} in {namespace} is already approved (phase: {installPlanPhase})")
        return installPlanResource

    if installPlanPhase == "Failed":
        conditions = getattr(installPlanResource.status, "conditions", None) or []
        raise OLMException(f"InstallPlan {installPlanName} in {namespace} has failed and cannot be approved: {conditions}")

    logger.info(f"Approving InstallPlan {installPlanName} in {namespace}")
    installPlanResource.spec.approved = True
    return installPlanAPI.patch(
        body=installPlanResource,
        name=installPlanName,
        namespace=namespace,
        content_type="application/merge-patch+json",
    )


def waitForInstallPlanComplete(
    dynClient: DynamicClient,
    namespace: str,
    installPlanName: str,
    timeout: Optional[int] = None,
    pollInterval: int = 30,
):
    """Wait for an InstallPlan to reach phase Complete.

    Polls the InstallPlan until its phase is Complete. An InstallPlan awaiting
    approval (phase RequiresApproval) is waited on as well, on the expectation
    that it will be approved out-of-band.

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace containing the InstallPlan
        installPlanName (str): Name of the InstallPlan to wait for
        timeout (int, optional): Maximum seconds to wait before raising
            OLMTimeoutError. None waits indefinitely. Defaults to None.
        pollInterval (int, optional): Seconds between polls. Defaults to 30.

    Returns:
        InstallPlan: The InstallPlan resource once its phase is Complete

    Raises:
        OLMException: If the InstallPlan phase is Failed
        OLMTimeoutError: If the timeout expires before the phase is Complete
        NotFoundError: If the InstallPlan does not exist
    """
    installPlanAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="InstallPlan")
    startTime = time()

    while True:
        installPlanResource = installPlanAPI.get(name=installPlanName, namespace=namespace)
        installPlanPhase = getattr(installPlanResource.status, "phase", None)

        if installPlanPhase == "Complete":
            logger.debug(f"InstallPlan {installPlanName} in {namespace} is complete")
            return installPlanResource

        if installPlanPhase == "Failed":
            conditions = getattr(installPlanResource.status, "conditions", None) or []
            raise OLMException(f"InstallPlan {installPlanName} in {namespace} has failed: {conditions}")

        if installPlanPhase == "RequiresApproval":
            logger.debug(f"InstallPlan {installPlanName} in {namespace} is awaiting approval")

        if timeout is not None and (time() - startTime) >= timeout:
            raise OLMTimeoutError(f"Timed out waiting for InstallPlan {installPlanName} in {namespace} to complete (phase: {installPlanPhase})")

        sleep(pollInterval)


def waitForSubscriptionStable(
    dynClient: DynamicClient,
    namespace: str,
    packageName: str,
    timeout: Optional[int] = None,
    pollInterval: int = 30,
    targetCSV: Optional[str] = None,
):
    """Wait for a Subscription to reach a stable state.

    Polls the Subscription until its state is AtLatestKnown, or until it is
    UpgradePending with the installed CSV matching targetCSV (the state reached
    after a Manual-approval install to a specific CSV, when newer versions
    remain unapproved).

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace containing the Subscription
        packageName (str): Name of the operator package
        timeout (int, optional): Maximum seconds to wait before raising
            OLMTimeoutError. None waits indefinitely. Defaults to None.
        pollInterval (int, optional): Seconds between polls. Defaults to 30.
        targetCSV (str, optional): When set, an UpgradePending state with
            installedCSV equal to this value is also considered stable. Defaults to None.

    Returns:
        Subscription: The Subscription resource once it is stable

    Raises:
        OLMException: If no Subscription exists for packageName in the namespace
        OLMTimeoutError: If the timeout expires before the Subscription is stable
    """
    subscriptionResource = getSubscription(dynClient, namespace, packageName)
    if subscriptionResource is None:
        raise OLMException(f"No subscription found for {packageName} in {namespace}")

    name = subscriptionResource.metadata.name
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")
    startTime = time()

    while True:
        subscriptionResource = subscriptionsAPI.get(name=name, namespace=namespace)
        state = getattr(subscriptionResource.status, "state", None)

        if state == "AtLatestKnown":
            logger.debug(f"Subscription {name} in {namespace} reached state: {state}")
            return subscriptionResource

        if targetCSV is not None and state == "UpgradePending":
            installedCSV = getattr(subscriptionResource.status, "installedCSV", None)
            if installedCSV == targetCSV:
                logger.debug(f"Subscription {name} in {namespace} reached state: {state} with installedCSV: {installedCSV}")
                return subscriptionResource

        if timeout is not None and (time() - startTime) >= timeout:
            raise OLMTimeoutError(f"Timed out waiting for Subscription {name} in {namespace} to become stable (state: {state})")

        sleep(pollInterval)


def _listSubscriptions(dynClient: DynamicClient, namespace: str) -> list:
    """List the Subscriptions in a namespace (empty when it does not exist)."""
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")
    try:
        return list(subscriptionsAPI.get(namespace=namespace).items)
    except NotFoundError:
        return []


def _listInstallPlans(dynClient: DynamicClient, namespace: str) -> list:
    """List the InstallPlans in a namespace (empty when it does not exist)."""
    installPlanAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="InstallPlan")
    try:
        return list(installPlanAPI.get(namespace=namespace).items)
    except NotFoundError:
        return []


def _namespaceApprovalStatus(namespace: str, subscriptions: list, installPlanResources: list) -> dict:
    """Compute the namespace approval status from already-fetched resources.

    The pure computation behind getNamespaceApprovalStatus, shared with
    getNamespaceConvergenceStatus so one snapshot costs one Subscription list
    and one InstallPlan list.
    """
    modes = {getattr(subscription.spec, "installPlanApproval", None) or "Automatic" for subscription in subscriptions}
    if len(modes) == 0:
        approvalMode = None
    elif len(modes) == 1:
        approvalMode = next(iter(modes))
    else:
        approvalMode = "Mixed"

    pendingApprovals = [
        _describePendingInstallPlan(installPlanResource, subscriptions)
        for installPlanResource in installPlanResources
        if getattr(installPlanResource.status, "phase", None) == "RequiresApproval"
    ]

    return {
        "namespace": namespace,
        "approvalMode": approvalMode,
        "pendingApprovals": pendingApprovals,
        "blocking": len(pendingApprovals) > 0,
    }


def getNamespaceApprovalStatus(dynClient: DynamicClient, namespace: str) -> dict:
    """Get the manual approval status of a namespace.

    Non-blocking snapshot intended as a gate check at the start of a processing
    step: reports the namespace's effective approval mode, the InstallPlans
    currently awaiting approval, and whether any of them gates further
    processing. A namespace whose Subscriptions use a mix of approval modes is
    reported with approvalMode "Mixed" rather than raised: OLM permits
    per-Subscription modes and auto-creates dependency Subscriptions that can
    legitimately introduce a mix. For waiting semantics a Mixed namespace
    behaves the same as Manual.

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to inspect

    Returns:
        dict: Namespace approval status with keys namespace (str), approvalMode
            ("Manual", "Automatic", "Mixed", or None when the namespace has no
            Subscriptions), pendingApprovals (list of approval info dicts as
            produced by getPendingInstallPlans) and blocking (bool, True when
            any InstallPlan is awaiting approval)
    """
    return _namespaceApprovalStatus(namespace, _listSubscriptions(dynClient, namespace), _listInstallPlans(dynClient, namespace))


def isApprovalRequired(dynClient: DynamicClient, namespace: str) -> bool:
    """Check whether any InstallPlan in a namespace is awaiting approval.

    The cheapest possible gate check for automation that only needs a yes/no
    answer: a single InstallPlan list per call. Callers that also need to know
    what is awaiting approval should use getNamespaceApprovalStatus instead.

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to check

    Returns:
        bool: True when any InstallPlan in the namespace is in phase
            RequiresApproval
    """
    installPlanAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="InstallPlan")
    try:
        installPlanResources = installPlanAPI.get(namespace=namespace)
    except NotFoundError:
        return False
    return any(getattr(installPlanResource.status, "phase", None) == "RequiresApproval" for installPlanResource in installPlanResources.items)


def waitForNamespaceApprovals(
    dynClient: DynamicClient,
    namespace: str,
    timeout: Optional[int] = None,
    pollInterval: int = 30,
    onPending: Optional[Callable] = None,
) -> dict:
    """Wait until a namespace has no InstallPlans awaiting approval.

    Polls getNamespaceApprovalStatus until nothing is blocking. This is
    explicitly the blocking variant of the approval interaction: a None
    timeout waits indefinitely, which is only appropriate when the caller has
    decided an in-process wait is acceptable (for example an attended
    rollout) — pass a bounded timeout otherwise.

    While approvals are pending, onPending (when supplied) is invoked on every
    poll with the current status dict and the 1-based poll number; returning
    False from onPending aborts the wait and the current, still-blocking
    status is returned. This is the hook point for caller-owned notifications.

    There is no special result or exception for "still awaiting approval": the
    blocking field of the returned status tells the caller whether the
    approvals were completed, and how to handle each situation is the caller's
    decision.

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to wait on
        timeout (int, optional): Maximum seconds to wait before raising
            OLMTimeoutError. None waits indefinitely. Defaults to None.
        pollInterval (int, optional): Seconds between polls. Defaults to 30.
        onPending (Callable, optional): Callback invoked as
            onPending(status, pollCount) on every poll while approvals are
            pending; returning False aborts the wait. Defaults to None.

    Returns:
        dict: The final namespace approval status (see
            getNamespaceApprovalStatus); when onPending aborted the wait this
            is the still-blocking status at the point of the abort

    Raises:
        OLMTimeoutError: If the timeout expires before the namespace has no
            InstallPlans awaiting approval
    """
    startTime = time()
    pollCount = 0

    while True:
        status = getNamespaceApprovalStatus(dynClient, namespace)
        if not status["blocking"]:
            return status

        pollCount += 1
        logger.debug(f"Namespace {namespace} has {len(status['pendingApprovals'])} install plans awaiting approval (poll {pollCount})")
        if onPending is not None and onPending(status, pollCount) is False:
            logger.info(f"Wait for approvals in namespace {namespace} aborted by the onPending callback (poll {pollCount})")
            return status

        if timeout is not None and (time() - startTime) >= timeout:
            raise OLMTimeoutError(f"Timed out waiting for approvals in namespace {namespace} ({len(status['pendingApprovals'])} install plans still pending)")

        sleep(pollInterval)


# How long to wait for Subscription statuses to settle before concluding that
# no change is coming (seconds), and how many consecutive identical status
# snapshots count as settled
SUBSCRIPTION_RESOLUTION_TIMEOUT = 600
SUBSCRIPTION_RESOLUTION_QUIET_POLLS = 4


def _getCachedPackageManifest(dynClient: DynamicClient, packageName: str, catalogSourceNamespace: str, manifestCache: dict):
    """Fetch a PackageManifest once per (package, catalog namespace) per snapshot.

    The poll loop resolves the channel head of every Subscription in a
    namespace on every poll; this cache keeps that at one manifest GET per
    package per poll. Deliberately quiet (no info logging): unlike the
    one-off getPackageManifest, this runs in a loop for hours under Manual
    approval.
    """
    cacheKey = (packageName, catalogSourceNamespace)
    if cacheKey not in manifestCache:
        packagemanifestAPI = dynClient.resources.get(api_version="packages.operators.coreos.com/v1", kind="PackageManifest")
        try:
            manifestCache[cacheKey] = packagemanifestAPI.get(name=packageName, namespace=catalogSourceNamespace)
        except NotFoundError:
            manifestCache[cacheKey] = None
    return manifestCache[cacheKey]


def _subscriptionChannelHead(dynClient: DynamicClient, subscription, manifestCache: dict) -> "tuple[Optional[str], Optional[str]]":
    """Resolve one Subscription's convergence target (the channel head CSV).

    The package, channel and catalog namespace come from the Subscription's
    own spec, so the target is derived from the same catalog the Subscription
    resolves against.

    Returns:
        tuple: (targetCSV, skipReason) -- targetCSV is None with skipReason
            set when no target can be derived (no PackageManifest for the
            package, or the channel is absent from it)
    """
    packageName = getattr(subscription.spec, "name", None)
    channel = getattr(subscription.spec, "channel", None)
    sourceNamespace = getattr(subscription.spec, "sourceNamespace", None) or "openshift-marketplace"

    if not packageName or not channel:
        return None, "Subscription has no package name or channel to resolve a target from"

    manifest = _getCachedPackageManifest(dynClient, packageName, sourceNamespace, manifestCache)
    if manifest is None:
        return None, f"no PackageManifest for package '{packageName}' in {sourceNamespace} (catalog removed or not yet available)"

    targetCSV = _channelHeadFromManifest(manifest, channel)
    if targetCSV is None:
        return None, f"channel '{channel}' not found in the PackageManifest for package '{packageName}'"
    return targetCSV, None


def _subscriptionResolutionError(subscription) -> Optional[str]:
    """The message of a Subscription's ResolutionFailed condition, when active.

    A Subscription that cannot resolve (bad channel, missing dependency,
    catalog problem) will never converge; waiting for it only burns the
    timeout. This is the fail-fast signal for that case.
    """
    conditions = getattr(getattr(subscription, "status", None), "conditions", None) or []
    for condition in conditions:
        if getattr(condition, "type", None) == "ResolutionFailed" and str(getattr(condition, "status", None)).lower() == "true":
            return getattr(condition, "message", None) or "resolution failed"
    return None


def getNamespaceConvergenceStatus(dynClient: DynamicClient, namespace: str) -> dict:
    """Get the convergence status of every Subscription in a namespace.

    Non-blocking snapshot. Each Subscription's target is the currentCSV of
    its channel in the operator's PackageManifest (see getChannelHeadCSV);
    the Subscription has converged when its status.installedCSV equals that
    target. InstallPlans are namespace-scoped, so every Subscription in the
    namespace is considered: just because the Subscription a role created
    has converged does not mean a sibling's plan is not still pending.

    Subscriptions with no derivable target (no PackageManifest, or the
    channel is absent from it) are skipped with a warning and never block:
    nothing can be approved for them, and a removed catalog must not wedge
    installs. Note the ordering interaction with resolution errors: a missing
    manifest is itself a resolution failure, so it is treated as a skip,
    while a manifest present alongside a ResolutionFailed condition is a
    hard error surfaced via the resolutionError field.

    The namespace approval status (approvalMode, pendingApprovals, blocking)
    is included unchanged -- the pending InstallPlans are the human-facing
    notices during the convergence wait, not the wait condition.

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to inspect

    Returns:
        dict: The namespace approval status (see getNamespaceApprovalStatus)
            extended with subscriptions (list of per-Subscription dicts with
            name, package, channel, state, installedCSV, targetCSV,
            installPlanRef, converged (bool, or None when skipped), skipped,
            skipReason and resolutionError), failedInstallPlans (names of
            Failed-phase InstallPlans referenced by non-converged
            Subscriptions) and converged (bool, True when every non-skipped
            Subscription's installedCSV equals its channel head)
    """
    subscriptions = _listSubscriptions(dynClient, namespace)
    installPlanResources = _listInstallPlans(dynClient, namespace)
    installPlansByName = {installPlan.metadata.name: installPlan for installPlan in installPlanResources}
    status = _namespaceApprovalStatus(namespace, subscriptions, installPlanResources)

    manifestCache = {}
    subscriptionStatuses = []
    failedInstallPlans = []

    for subscription in subscriptions:
        targetCSV, skipReason = _subscriptionChannelHead(dynClient, subscription, manifestCache)
        if skipReason is not None:
            logger.warning(
                f"Cannot determine the channel head for Subscription {subscription.metadata.name} in {namespace}: {skipReason}; "
                "treating it as converged for approval purposes"
            )

        installedCSV = getattr(subscription.status, "installedCSV", None)
        installPlanRefName = getattr(getattr(subscription.status, "installPlanRef", None), "name", None)
        converged = None if skipReason is not None else (installedCSV == targetCSV)

        if converged is False and installPlanRefName is not None:
            referencedPlan = installPlansByName.get(installPlanRefName)
            if referencedPlan is not None and getattr(referencedPlan.status, "phase", None) == "Failed":
                failedInstallPlans.append(installPlanRefName)

        subscriptionStatuses.append(
            {
                "name": subscription.metadata.name,
                "package": getattr(subscription.spec, "name", None),
                "channel": getattr(subscription.spec, "channel", None),
                "state": getattr(subscription.status, "state", None),
                "installedCSV": installedCSV,
                "targetCSV": targetCSV,
                "installPlanRef": installPlanRefName,
                "converged": converged,
                "skipped": skipReason is not None,
                "skipReason": skipReason,
                # A missing manifest is itself a resolution failure: the skip
                # wins and suppresses the error, so a removed catalog warns
                # rather than fails the wait
                "resolutionError": None if skipReason is not None else _subscriptionResolutionError(subscription),
            }
        )

    status["subscriptions"] = subscriptionStatuses
    status["failedInstallPlans"] = failedInstallPlans
    status["converged"] = all(entry["converged"] is not False for entry in subscriptionStatuses)
    return status


def _formatConvergenceTimeoutMessage(namespace: str, status: dict, timeout: int) -> str:
    """The actionable per-Subscription breakdown for a convergence timeout."""
    lines = [f"Timed out after {timeout}s waiting for Subscriptions in {namespace} to reach their channel head:"]
    for entry in status["subscriptions"]:
        if entry["converged"] is False:
            lines.append(f"  {entry['name']}: {entry['installedCSV'] or '(not installed)'} -> {entry['targetCSV']} (state: {entry['state']})")
        elif entry["skipped"]:
            lines.append(f"  {entry['name']}: skipped ({entry['skipReason']})")
    return "\n".join(lines)


def waitForSubscriptionConvergence(
    dynClient: DynamicClient,
    namespace: str,
    timeout: Optional[int] = None,
    pollInterval: int = 30,
    onPending: Optional[Callable] = None,
) -> dict:
    """Wait until every Subscription in a namespace has reached its channel head.

    The deterministic replacement for timing-window waits: the target state
    (each Subscription's channel head, from the PackageManifest) is known up
    front, so there is no window in which a just-created or just-patched
    Subscription can be mistaken for a settled one -- a Subscription that has
    not converged is simply not done, whether its InstallPlan has not been
    generated yet, is awaiting approval, or is still installing.

    Fails fast, in both approval modes, on Subscriptions that can never
    converge: an active ResolutionFailed condition, or a Failed InstallPlan
    referenced by a non-converged Subscription, raises OLMException
    immediately rather than burning the timeout.

    While Subscriptions are unconverged, onPending (when supplied) is invoked
    on every poll with the current status dict and the 1-based poll number;
    returning False from onPending aborts the wait and the current,
    non-converged status is returned. This is the hook point for
    caller-owned notifications (manual approval notices, status lines).

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to wait in
        timeout (int, optional): Maximum seconds to wait before raising
            OLMTimeoutError. None waits indefinitely. Defaults to None.
        pollInterval (int, optional): Seconds between polls. Defaults to 30.
        onPending (Callable, optional): Callback invoked as
            onPending(status, pollCount) on every poll while Subscriptions
            are unconverged; returning False aborts the wait. Defaults to
            None.

    Returns:
        dict: The final namespace convergence status (see
            getNamespaceConvergenceStatus); when onPending aborted the wait
            this is the still-non-converged status at the point of the abort

    Raises:
        OLMException: When a Subscription has an active ResolutionFailed
            condition or a referenced InstallPlan has Failed
        OLMTimeoutError: If the timeout expires with Subscriptions still
            unconverged (the message lists each one as
            name: installedCSV -> targetCSV)
    """
    startTime = time()
    pollCount = 0

    while True:
        status = getNamespaceConvergenceStatus(dynClient, namespace)

        for entry in status["subscriptions"]:
            if entry["resolutionError"]:
                raise OLMException(
                    f"Subscription {entry['name']} in {namespace} failed to resolve: {entry['resolutionError']}. "
                    f"Check 'oc get subscription {entry['name']} -n {namespace} -o yaml' and the health of the "
                    "catalog and operator-lifecycle-manager pods"
                )
        if status["failedInstallPlans"]:
            raise OLMException(
                f"InstallPlan(s) {', '.join(status['failedInstallPlans'])} have Failed in namespace {namespace}; "
                f"check with 'oc describe installplan <name> -n {namespace}'"
            )

        if status["converged"]:
            return status

        pollCount += 1
        unconverged = [entry["name"] for entry in status["subscriptions"] if entry["converged"] is False]
        logger.debug(f"Waiting for {len(unconverged)} Subscription(s) to reach their channel head in {namespace}: {', '.join(unconverged)} (poll {pollCount})")
        if onPending is not None and onPending(status, pollCount) is False:
            logger.info(f"Wait for Subscription convergence in namespace {namespace} aborted by the onPending callback (poll {pollCount})")
            return status

        if timeout is not None and (time() - startTime) >= timeout:
            raise OLMTimeoutError(_formatConvergenceTimeoutMessage(namespace, status, timeout))

        sleep(pollInterval)


def _subscriptionResolutionFingerprint(subscription) -> tuple:
    """The Subscription status fields that change when OLM resolves an update.

    Everything is stringified so snapshots of subscriptions in mixed states
    (for example a None state against an UpgradePending one) remain sortable
    and comparable. Fields that churn for unrelated reasons (catalogHealth
    most notably) are deliberately not part of the fingerprint.
    """
    status = getattr(subscription, "status", None)
    return (
        str(subscription.metadata.namespace),
        str(subscription.metadata.name),
        str(getattr(status, "state", None)),
        str(getattr(getattr(status, "installPlanRef", None), "name", None)),
        str(getattr(status, "installedCSV", None)),
        str(getattr(status, "installPlanGeneration", None)),
        str(getattr(status, "currentCSV", None)),
    )


def waitForSubscriptionResolution(
    dynClient: DynamicClient,
    namespace: Optional[str] = None,
    timeout: int = SUBSCRIPTION_RESOLUTION_TIMEOUT,
    pollInterval: int = 15,
    quietPolls: int = SUBSCRIPTION_RESOLUTION_QUIET_POLLS,
):
    """Wait for Subscription statuses to settle.

    Polls the Subscriptions in scope (one namespace, or the whole cluster when
    namespace is None) until their resolution status -- state, installPlanRef,
    installedCSV, installPlanGeneration and currentCSV -- has been identical
    for quietPolls consecutive snapshots. OLM re-resolves Subscriptions within
    seconds of a catalog update or a Subscription spec change, so a period of
    quiet is evidence that nothing new is coming: an update that is coming
    churns these fields (a pending upgrade under Manual approval flips state
    to UpgradePending and installs a new installPlanRef), while no update
    leaves them untouched.

    This is the settle signal for approval gates that must distinguish "no
    InstallPlan is pending yet" from "no InstallPlan is coming" -- a
    distinction a single snapshot cannot make.

    The timeout is deliberately not fatal: expiring mid-churn logs a warning
    and returns, because "nothing more is coming" is a legitimate outcome the
    poll cannot disprove, and the caller proceeds with whatever is visible.

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str, optional): Restrict the settle poll to one namespace.
            None polls every Subscription in the cluster. Defaults to None.
        timeout (int, optional): Maximum seconds to wait before returning.
            Defaults to 600.
        pollInterval (int, optional): Seconds between polls. Defaults to 15.
        quietPolls (int, optional): Consecutive identical snapshots that
            conclude the settle. Defaults to 4 (~1 minute).

    Returns:
        list: The final per-Subscription resolution fingerprints, sorted
    """
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")
    startTime = time()
    stablePolls = 0
    previous = None
    scope = "cluster-wide" if namespace is None else f"namespace {namespace}"

    while True:
        try:
            if namespace is None:
                subscriptions = list(subscriptionsAPI.get().items)
            else:
                subscriptions = list(subscriptionsAPI.get(namespace=namespace).items)
        except NotFoundError:
            return []

        fingerprints = sorted(_subscriptionResolutionFingerprint(subscription) for subscription in subscriptions)
        if fingerprints == previous:
            stablePolls += 1
        else:
            stablePolls = 1
            previous = fingerprints

        if stablePolls >= quietPolls:
            logger.debug(f"Subscription status {scope} has been stable for {stablePolls} polls")
            return fingerprints

        if (time() - startTime) >= timeout:
            logger.warning(f"Subscription status {scope} was still changing after {timeout}s; " "continuing with whatever InstallPlans are currently pending")
            return fingerprints

        sleep(pollInterval)


def _validateNamespaceApprovalConsistency(
    dynClient: DynamicClient,
    namespace: str,
    packageName: str,
    installPlanApproval: str,
) -> None:
    """Warn when setting an approval mode will create a mixed namespace.

    Lists the Subscriptions in the namespace (excluding the one being applied for
    packageName) and logs a warning when any of them uses a different approval
    mode. A mixed namespace is valid -- OLM auto-creates dependency Subscriptions
    that can legitimately introduce a mix -- and behaves the same as Manual for
    waiting semantics (InstallPlans in RequiresApproval gate processing regardless
    of which Subscription generated them), so this is informational only.

    Args:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to check
        packageName (str): Package of the Subscription being applied, which is
            excluded from the check
        installPlanApproval (str): The approval mode about to be applied
    """
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")
    try:
        subscriptions = subscriptionsAPI.get(namespace=namespace)
    except NotFoundError:
        return

    conflicting = []
    for subscription in subscriptions.items:
        # The Subscription being applied is matched by package name (spec.name) or resource name
        if getattr(subscription.spec, "name", None) == packageName or subscription.metadata.name == packageName:
            continue
        mode = getattr(subscription.spec, "installPlanApproval", None) or "Automatic"
        if mode != installPlanApproval:
            conflicting.append(f"{subscription.metadata.name} ({mode})")

    if conflicting:
        logger.warning(
            f"Setting installPlanApproval to '{installPlanApproval}' for {packageName} in {namespace} will leave the namespace with a mix of "
            f"approval modes ({', '.join(conflicting)}). A mixed namespace is valid and behaves the same as Manual for waiting semantics"
        )


def _shouldReleaseForApproval(onApprovalRequired, approvalInfo: dict) -> bool:
    """Decide whether applySubscription should stop waiting and return a pending approval.

    For the "return" mode this is always true. For a callable, the callable is
    invoked with the approval info and a return value of False releases the
    caller from the wait; any other return value continues waiting.

    Args:
        onApprovalRequired (Union[str, Callable]): The approval handling mode or callback
        approvalInfo (dict): Approval info for the InstallPlan awaiting approval

    Returns:
        bool: True when the caller should be released from the wait with the
            pending approval info
    """
    if callable(onApprovalRequired):
        return onApprovalRequired(approvalInfo) is False
    return True


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
    autoApproveInitialInstall: Optional[bool] = None,
    onApprovalRequired: Union[str, Callable] = "wait",
    pollInterval: int = 30,
):
    """Create or update an operator subscription in a namespace.

    Automatically detects default channel and catalog source from PackageManifest if not provided.
    Ensures an OperatorGroup exists before creating the subscription.

    When installPlanApproval is set to "Manual" and a startingCSV is specified, this function will
    by default automatically approve the InstallPlan for the first-time installation to move to
    that startingCSV. Subsequent upgrades will still require manual approval. This legacy behavior
    can be disabled with autoApproveInitialInstall=False.

    The onApprovalRequired parameter controls what happens when an InstallPlan is awaiting
    approval and this function is not auto-approving it: "wait" (default) polls until the
    approval is given out-of-band, "return" immediately returns the pending approval info, and
    a callable is invoked with the approval info (returning False from the callable has the
    same effect as "return"). When released via "return" or a callable returning False, the
    function returns a (subscription, approvalInfo) tuple instead of just the subscription.

    When onApprovalRequired is not "wait" or autoApproveInitialInstall is set, the function
    also checks the namespace for Subscriptions using a different approval mode and logs a
    warning when one is found. A mixed namespace is valid -- OLM auto-creates dependency
    Subscriptions that can introduce a mix -- and behaves the same as Manual for waiting
    semantics, so this is informational only.

    Args:
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
            the first InstallPlan to this CSV will be automatically approved unless disabled via
            autoApproveInitialInstall. Defaults to None.
        autoApproveInitialInstall (bool, optional): Whether to auto-approve the initial InstallPlan to
            startingCSV under Manual approval. None preserves the legacy behavior (auto-approve when
            Manual and startingCSV are set), True forces it on, False disables it. Only valid when
            installPlanApproval is "Manual". Defaults to None.
        onApprovalRequired (Union[str, Callable], optional): Controls handling of InstallPlans awaiting
            approval: "wait" polls until approved out-of-band, "return" returns the pending approval
            info, a callable receives the approval info and releases the caller when it returns False.
            Defaults to "wait".
        pollInterval (int, optional): Seconds between polls while waiting. Defaults to 30.

    Returns:
        Subscription: The created or updated subscription resource, or a
            (Subscription, dict) tuple when released from waiting via the "return"
            approval mode or a callable returning False

    Raises:
        OLMException: If the package is not available in any catalog, if installPlanApproval is
            "Manual" without a startingCSV (unless new-style approval handling is opted in to),
            if autoApproveInitialInstall is used without Manual approval, or if onApprovalRequired
            is invalid
        NotFoundError: If resources cannot be created
    """
    # Validate the new-style approval handling parameters
    if autoApproveInitialInstall is not None and installPlanApproval != "Manual":
        raise OLMException("autoApproveInitialInstall is only valid when installPlanApproval is 'Manual'")
    if onApprovalRequired != "wait" and onApprovalRequired != "return" and not callable(onApprovalRequired):
        raise OLMException("onApprovalRequired must be 'wait', 'return', or a callable")

    # Legacy validation, retained for backward compatibility: Manual approval requires a
    # startingCSV unless the caller has opted in to the new-style approval handling
    newStyleApprovalHandling = autoApproveInitialInstall is not None or onApprovalRequired != "wait"
    if installPlanApproval == "Manual" and startingCSV is None and not newStyleApprovalHandling:
        raise OLMException("When installPlanApproval is 'Manual', a startingCSV must be provided")

    # By default (None) the initial InstallPlan to startingCSV is auto-approved when
    # installPlanApproval is "Manual" and a startingCSV is provided (legacy behavior)
    autoApproveInitial = autoApproveInitialInstall is not False

    # Warn when the requested approval mode differs from other Subscriptions in the
    # namespace. Mixed namespaces are valid (OLM auto-creates dependency Subscriptions
    # with a different mode) and behave the same as Manual for waiting semantics, so
    # this is informational only.
    if installPlanApproval is not None and newStyleApprovalHandling:
        _validateNamespaceApprovalConsistency(dynClient, namespace, packageName, installPlanApproval)

    if catalogSourceNamespace is None:
        catalogSourceNamespace = "openshift-marketplace"

    labelSelector = f"operators.coreos.com/{packageName}.{namespace}"
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(loader=FileSystemLoader(searchpath=templateDir))

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
        catalog_namespace=catalogSourceNamespace,
        install_plan_approval=installPlanApproval,
        starting_csv=startingCSV,
    )
    subscription = yaml.safe_load(renderedTemplate)

    # apply should work regardless of if the subscription already exists or not,
    # however if two parallel processes call it at the same time it can result
    # in a 409 error in that case trying again will resolve the issue
    try:
        applyResource(
            dynClient=dynClient,
            apiVersion="operators.coreos.com/v1alpha1",
            kind="Subscription",
            body=subscription,
            namespace=namespace,
        )
    except Exception as e:
        if "409" in str(e) or "AlreadyExists" in str(e):
            logger.warning(f"Subscription {name} already exists and produced a conflict, retrying the apply")
            applyResource(
                dynClient=dynClient,
                apiVersion="operators.coreos.com/v1alpha1",
                kind="Subscription",
                body=subscription,
                namespace=namespace,
            )
        else:
            raise

    # Wait for InstallPlan to be created
    logger.debug(f"Waiting for {packageName}.{namespace} InstallPlans")
    installPlanAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="InstallPlan")

    # Use label selector to get InstallPlans (standard approach)
    installPlanResources = installPlanAPI.get(label_selector=labelSelector, namespace=namespace)
    while len(installPlanResources.items) == 0:
        installPlanResources = installPlanAPI.get(label_selector=labelSelector, namespace=namespace)
        sleep(pollInterval)

    if len(installPlanResources.items) == 0:
        raise OLMException(f"Found 0 InstallPlans for {packageName}")
    elif len(installPlanResources.items) > 1:
        logger.warning(f"More than 1 InstallPlan found for {packageName} using label selector")

    # Select the InstallPlan to use
    installPlanResource = None

    # Special handling for Manual approval with startingCSV
    if installPlanApproval == "Manual" and startingCSV is not None:
        logger.debug(f"Manual approval with startingCSV {startingCSV} - checking if label selector returned correct InstallPlan")

        # Check if any of the InstallPlans from label selector match the startingCSV
        for plan in installPlanResources.items:
            csvNames = getattr(plan.spec, "clusterServiceVersionNames", [])
            logger.debug(f"InstallPlan {plan.metadata.name} (from label selector) contains CSVs: {csvNames}")
            if csvNames and startingCSV in csvNames:
                installPlanResource = plan
                logger.info(f"Found InstallPlan {plan.metadata.name} matching startingCSV {startingCSV} via label selector")
                break

        # If no match found via label selector, search all InstallPlans owned by this subscription
        if installPlanResource is None:
            logger.warning(f"Label selector did not return InstallPlan matching startingCSV {startingCSV}")
            logger.debug(f"Searching all InstallPlans in {namespace} owned by subscription {name}")

            allInstallPlans = installPlanAPI.get(namespace=namespace)
            for plan in allInstallPlans.items:
                # Check if this InstallPlan is owned by our subscription
                owner_refs = getattr(plan.metadata, "ownerReferences", [])
                is_owned_by_subscription = any(ref.kind == "Subscription" and ref.name == name for ref in owner_refs)

                if is_owned_by_subscription:
                    csvNames = getattr(plan.spec, "clusterServiceVersionNames", [])
                    logger.debug(f"InstallPlan {plan.metadata.name} (owned by subscription) contains CSVs: {csvNames}")
                    if csvNames and startingCSV in csvNames:
                        installPlanResource = plan
                        logger.info(f"Found InstallPlan {plan.metadata.name} matching startingCSV {startingCSV} via subscription ownership")
                        break

            if installPlanResource is None:
                logger.warning(f"No InstallPlan found matching startingCSV {startingCSV}, using first from label selector")
                installPlanResource = installPlanResources.items[0]
    else:
        # Standard case: use first InstallPlan from label selector
        installPlanResource = installPlanResources.items[0]

    installPlanName = installPlanResource.metadata.name
    installPlanPhase = installPlanResource.status.phase

    # If the InstallPlan for our startingCSV is already Complete, we're done
    if installPlanPhase == "Complete":
        logger.info(f"InstallPlan {installPlanName} for {startingCSV} is already Complete")
    else:
        # Wait for InstallPlan to complete
        logger.debug(f"Waiting for InstallPlan {installPlanName}")

        # Track if we've already approved this install plan
        approved_manual_install = False

        while installPlanPhase != "Complete":
            installPlanResource = installPlanAPI.get(name=installPlanName, namespace=namespace)
            installPlanPhase = getattr(installPlanResource.status, "phase", None)

            # If InstallPlan requires approval and this is the first installation to startingCSV
            if installPlanPhase == "RequiresApproval":
                csvNames = list(getattr(installPlanResource.spec, "clusterServiceVersionNames", None) or [])
                if (
                    installPlanApproval == "Manual"
                    and startingCSV is not None
                    and autoApproveInitial
                    and not approved_manual_install
                    and startingCSV in csvNames
                ):
                    logger.info(f"Approving InstallPlan {installPlanName} for first-time installation to {startingCSV}")
                    approveInstallPlan(dynClient, namespace, installPlanName)
                    approved_manual_install = True
                elif onApprovalRequired != "wait":
                    # The caller has opted in to being released from the wait while an
                    # approval is outstanding
                    subscriptionResource = subscriptionsAPI.get(name=name, namespace=namespace)
                    approvalInfo = _describePendingInstallPlan(installPlanResource, [subscriptionResource])
                    if _shouldReleaseForApproval(onApprovalRequired, approvalInfo):
                        logger.info(f"InstallPlan {installPlanName} in {namespace} is awaiting approval")
                        return subscriptionResource, approvalInfo
                else:
                    if startingCSV is not None:
                        logger.debug(f"InstallPlan CSV {csvNames} does not match startingCSV {startingCSV}, waiting for manual approval")
                    else:
                        logger.debug(f"No startingCSV specified, InstallPlan {installPlanName} requires manual approval")

            sleep(pollInterval)

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
        elif state == "UpgradePending" and installPlanApproval == "Manual":
            # Verify the installed CSV matches the startingCSV
            installedCSV = getattr(subscriptionResource.status, "installedCSV", None)
            if startingCSV is not None and installedCSV == startingCSV:
                logger.debug(f"Subscription {name} in {namespace} reached state: {state} with installedCSV: {installedCSV}")
                return subscriptionResource

            # The Subscription is blocked on an upgrade that has not been approved
            if onApprovalRequired != "wait":
                approvalInfo = getPendingInstallPlan(dynClient, namespace, packageName)
                if approvalInfo is not None and _shouldReleaseForApproval(onApprovalRequired, approvalInfo):
                    logger.info(f"Subscription {name} in {namespace} is awaiting approval of an upgrade")
                    return subscriptionResource, approvalInfo
                elif approvalInfo is None:
                    logger.warning(f"Subscription {name} in {namespace} is in state {state} but no pending InstallPlan could be resolved, continuing to wait")
            elif startingCSV is not None:
                logger.debug(
                    f"Subscription {name} in {namespace} state is {state} but installedCSV ({installedCSV}) does not match startingCSV ({startingCSV}), retrying..."
                )

        logger.debug(f"Subscription {name} in {namespace} not ready yet (state = {state}), retrying...")
        sleep(pollInterval)


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
