# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

"""
Unit tests for the OLM manual approval primitives, approval handling modes and
namespace-level approval status.

These tests mock up the DynamicClient and its resource APIs rather than use
real resources: the code under test is polling loops around Kubernetes
resources, which are cheap to simulate and slow (or impossible, without a
cluster in a specific state) to exercise for real. The mocking conventions
follow test_olm_installplan_selection.py.
"""

from contextlib import contextmanager

import logging

import pytest
from unittest.mock import Mock, patch

from mas.devops.olm import (
    OLMException,
    OLMTimeoutError,
    approveInstallPlan,
    applySubscription,
    getClusterApprovalMode,
    getNamespaceApprovalStatus,
    getPendingInstallPlan,
    getPendingInstallPlans,
    getSubscriptionApprovalMode,
    getSubscriptionInstallPlanRefs,
    isApprovalRequired,
    waitForInstallPlanComplete,
    waitForNamespaceApprovals,
    waitForSubscriptionInstallPlans,
    waitForSubscriptionResolution,
    waitForSubscriptionStable,
)

SUBSCRIPTION_YAML = """
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: test-operator
  namespace: test-namespace
spec:
  channel: stable
  name: test-operator
  source: test-catalog
  sourceNamespace: openshift-marketplace
"""


class ResourceList:
    """Minimal stand-in for a Kubernetes resource list, providing just .items."""

    def __init__(self, items):
        self.items = items


class ResponseSequence:
    """Stateful get response that yields each item in turn, then repeats the last.

    Used to simulate phase transitions across the polling loops (for example
    an InstallPlan moving from RequiresApproval to Complete).
    """

    def __init__(self, responses):
        self._responses = list(responses)

    def __call__(self):
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


def makeSubscription(name, namespace, package, approval=None, state=None, installedCSV=None, installPlanRef=None, installPlanGeneration=None, currentCSV=None):
    """Build a mock Subscription with every attribute the code reads set explicitly.

    Mock auto-attributes are truthy, so attributes the implementation reads via
    getattr(..., default) must be assigned None explicitly for the default to
    apply (for example an unset spec.installPlanApproval must be None, not an
    auto-generated Mock).
    """
    subscription = Mock()
    subscription.metadata.name = name
    subscription.metadata.namespace = namespace
    subscription.spec.name = package
    subscription.spec.installPlanApproval = approval
    subscription.status.state = state
    subscription.status.installedCSV = installedCSV
    subscription.status.installPlanGeneration = installPlanGeneration
    subscription.status.currentCSV = currentCSV
    if installPlanRef is None:
        subscription.status.installPlanRef = None
    else:
        ref = Mock()
        ref.name = installPlanRef
        subscription.status.installPlanRef = ref
    return subscription


def makeOwnerRef(kind, name):
    """Build a mock ownerReference with just .kind and .name."""
    ownerRef = Mock()
    ownerRef.kind = kind
    ownerRef.name = name
    return ownerRef


def makeInstallPlan(
    name,
    namespace,
    csvNames,
    phase,
    labels=None,
    ownerRefs=None,
    approved=None,
    created="2026-11-15T10:00:00Z",
    conditions=None,
):
    """Build a mock InstallPlan with every attribute the code reads set explicitly."""
    installPlan = Mock()
    installPlan.metadata.name = name
    installPlan.metadata.namespace = namespace
    installPlan.metadata.labels = labels
    installPlan.metadata.ownerReferences = ownerRefs if ownerRefs is not None else []
    installPlan.metadata.creationTimestamp = created
    installPlan.spec.clusterServiceVersionNames = csvNames
    installPlan.spec.approved = approved
    installPlan.status.phase = phase
    installPlan.status.conditions = conditions
    return installPlan


def _resolve(response, default):
    if response is None:
        return default
    if isinstance(response, ResponseSequence):
        return response()
    return response


def makeGetHandler(labelResponse=None, nameResponse=None, namespaceResponse=None, allResponse=None):
    """Build a Mock API get side effect dispatching on the query kwargs.

    label_selector queries return ResourceList(labelResponse), name queries
    return nameResponse, namespace listings return ResourceList(namespaceResponse)
    and kwargs-free (all namespaces) queries return ResourceList(allResponse).
    Each response may be a static value (None defaults to an empty list, or a
    truthy Mock for name queries) or a ResponseSequence for stateful responses.
    """

    def handler(*args, **kwargs):
        if "label_selector" in kwargs:
            return ResourceList(_resolve(labelResponse, []))
        if "name" in kwargs:
            return _resolve(nameResponse, Mock())
        if "namespace" in kwargs:
            return ResourceList(_resolve(namespaceResponse, []))
        return ResourceList(_resolve(allResponse, []))

    return handler


def buildDynClient(subscriptionHandler, installPlanHandler):
    """Build a mock DynamicClient mapping Subscription and InstallPlan kinds to mock APIs.

    Returns:
        tuple: (client, subscriptionAPI, installPlanAPI) where the APIs are
            Mocks whose get side effects are the supplied handlers
    """
    client = Mock()
    subscriptionAPI = Mock()
    subscriptionAPI.get.side_effect = subscriptionHandler
    installPlanAPI = Mock()
    installPlanAPI.get.side_effect = installPlanHandler

    def resourcesGet(**kwargs):
        apis = {
            ("operators.coreos.com/v1alpha1", "Subscription"): subscriptionAPI,
            ("operators.coreos.com/v1alpha1", "InstallPlan"): installPlanAPI,
        }
        return apis.get((kwargs.get("api_version"), kwargs.get("kind")), Mock())

    client.resources.get.side_effect = resourcesGet
    return client, subscriptionAPI, installPlanAPI


@contextmanager
def applySubscriptionIsolation():
    """Patch the cluster and template interactions around applySubscription.

    applySubscription itself is not mocked: namespace creation, OperatorGroup
    management, PackageManifest lookup, polling sleeps and Jinja2 template
    rendering are patched so that only the approval logic under test runs.
    Both packageChannel and catalogSource must be passed by tests using this
    fixture so that the PackageManifest is never consulted.
    """
    env = Mock()
    template = Mock()
    template.render.return_value = SUBSCRIPTION_YAML
    env.get_template.return_value = template

    with (
        patch("mas.devops.olm.createNamespace"),
        patch("mas.devops.olm.ensureOperatorGroupExists"),
        patch("mas.devops.olm.getPackageManifest", return_value=None),
        patch("mas.devops.olm.sleep"),
        patch("mas.devops.olm.Environment", return_value=env),
    ):
        yield env


class TestGetSubscriptionApprovalMode:
    """Tests for getSubscriptionApprovalMode."""

    def test_unset_install_plan_approval_defaults_to_automatic(self):
        subscription = makeSubscription("test-operator", "test-namespace", "test-operator", approval=None)
        client, _, _ = buildDynClient(makeGetHandler(namespaceResponse=[subscription]), makeGetHandler())

        assert getSubscriptionApprovalMode(client, "test-namespace") == "Automatic"

    def test_explicit_manual_mode(self):
        subscription = makeSubscription("test-operator", "test-namespace", "test-operator", approval="Manual")
        client, _, _ = buildDynClient(makeGetHandler(namespaceResponse=[subscription]), makeGetHandler())

        assert getSubscriptionApprovalMode(client, "test-namespace") == "Manual"

    def test_mixed_modes_reported_as_mixed(self, caplog):
        manual = makeSubscription("manual-operator", "test-namespace", "manual-operator", approval="Manual")
        automatic = makeSubscription("automatic-operator", "test-namespace", "automatic-operator", approval=None)
        client, _, _ = buildDynClient(makeGetHandler(namespaceResponse=[manual, automatic]), makeGetHandler())

        with caplog.at_level(logging.WARNING, logger="mas.devops.olm"):
            mode = getSubscriptionApprovalMode(client, "test-namespace")

        assert mode == "Mixed"
        assert "Mixed install plan approval modes" in caplog.text
        assert "manual-operator" in caplog.text
        assert "automatic-operator" in caplog.text

    def test_empty_namespace_returns_none(self):
        client, _, _ = buildDynClient(makeGetHandler(namespaceResponse=[]), makeGetHandler())

        assert getSubscriptionApprovalMode(client, "test-namespace") is None


class TestGetClusterApprovalMode:
    """Tests for getClusterApprovalMode (cluster-wide / prefix-scoped aggregation)."""

    def test_all_automatic_cluster(self):
        """Every subscription Automatic (unset installPlanApproval defaults to Automatic)."""
        subscriptions = [
            makeSubscription("sub1", "ns1", "pkg1", approval=None),
            makeSubscription("sub2", "ns2", "pkg2", approval="Automatic"),
        ]
        client, _, _ = buildDynClient(makeGetHandler(allResponse=subscriptions), makeGetHandler())

        status = getClusterApprovalMode(client)

        assert status["approvalMode"] == "Automatic"
        assert status["counts"] == {"Automatic": 2}
        assert status["subscriptions"] == 2
        assert status["namespaces"] == ["ns1", "ns2"]

    def test_all_manual_cluster(self):
        subscriptions = [
            makeSubscription("sub1", "ns1", "pkg1", approval="Manual"),
            makeSubscription("sub2", "ns2", "pkg2", approval="Manual"),
        ]
        client, _, _ = buildDynClient(makeGetHandler(allResponse=subscriptions), makeGetHandler())

        status = getClusterApprovalMode(client)

        assert status["approvalMode"] == "Manual"
        assert status["counts"] == {"Manual": 2}

    def test_mixed_cluster_reported_with_counts(self):
        """Both modes present aggregates to Mixed with per-mode counts."""
        subscriptions = [
            makeSubscription("sub1", "ns1", "pkg1", approval=None),
            makeSubscription("sub2", "ns1", "pkg2", approval="Manual"),
            makeSubscription("sub3", "ns2", "pkg3", approval="Manual"),
        ]
        client, _, _ = buildDynClient(makeGetHandler(allResponse=subscriptions), makeGetHandler())

        status = getClusterApprovalMode(client)

        assert status["approvalMode"] == "Mixed"
        assert status["counts"] == {"Automatic": 1, "Manual": 2}
        assert status["subscriptions"] == 3

    def test_namespace_prefix_restricts_the_scope(self):
        """With a prefix only matching namespaces are inspected; the rest are ignored."""
        subscriptions = [
            makeSubscription("core", "mas-inst1-core", "ibm-mas", approval="Manual"),
            makeSubscription("app", "mas-inst1-manage", "ibm-mas-manage", approval=None),
            makeSubscription("dep", "ibm-sls", "ibm-sls", approval="Manual"),
        ]
        client, _, _ = buildDynClient(makeGetHandler(allResponse=subscriptions), makeGetHandler())

        status = getClusterApprovalMode(client, namespacePrefix="mas-inst1-")

        assert status["approvalMode"] == "Mixed"
        assert status["counts"] == {"Automatic": 1, "Manual": 1}
        assert status["subscriptions"] == 2
        assert status["namespaces"] == ["mas-inst1-core", "mas-inst1-manage"]

    def test_no_subscriptions_in_scope_returns_none(self):
        """A prefix matching nothing reports approvalMode None (nothing in scope)."""
        subscriptions = [makeSubscription("dep", "ibm-sls", "ibm-sls", approval="Manual")]
        client, _, _ = buildDynClient(makeGetHandler(allResponse=subscriptions), makeGetHandler())

        assert getClusterApprovalMode(client)["approvalMode"] == "Manual"
        assert getClusterApprovalMode(client, namespacePrefix="mas-inst1-")["approvalMode"] is None

    def test_empty_cluster_returns_none(self):
        client, _, _ = buildDynClient(makeGetHandler(allResponse=[]), makeGetHandler())

        status = getClusterApprovalMode(client)

        assert status["approvalMode"] is None
        assert status["counts"] == {}
        assert status["namespaces"] == []
        assert status["subscriptions"] == 0


class TestGetPendingInstallPlans:
    """Tests for getPendingInstallPlans."""

    def test_filters_to_requires_approval_and_enriches_via_owner_references(self):
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v1.0.0"
        )
        pending = makeInstallPlan(
            "install-plan-pending",
            "test-namespace",
            ["test-operator.v1.0.0", "test-operator.v2.0.0"],
            "RequiresApproval",
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        complete = makeInstallPlan("install-plan-complete", "test-namespace", ["test-operator.v0.9.0"], "Complete")
        installing = makeInstallPlan("install-plan-installing", "test-namespace", ["test-operator.v3.0.0"], "Installing")

        client, _, _ = buildDynClient(
            makeGetHandler(namespaceResponse=[subscription]),
            makeGetHandler(namespaceResponse=[pending, complete, installing]),
        )

        approvals = getPendingInstallPlans(client, "test-namespace")

        assert len(approvals) == 1
        assert approvals[0] == {
            "installPlan": "install-plan-pending",
            "namespace": "test-namespace",
            "subscription": "test-operator",
            "package": "test-operator",
            "csvNames": ["test-operator.v1.0.0", "test-operator.v2.0.0"],
            "currentCSV": "test-operator.v1.0.0",
            "targetCSV": "test-operator.v2.0.0",
            "created": "2026-11-15T10:00:00Z",
        }

    def test_resolves_subscription_via_label_fallback(self):
        # The InstallPlan has no ownerReferences but carries the OLM label;
        # the Subscription is matched by its spec.name (package) rather than
        # its resource name
        subscription = makeSubscription("test-operator-sub", "test-namespace", "test-operator")
        pending = makeInstallPlan(
            "install-plan-pending",
            "test-namespace",
            ["test-operator.v2.0.0"],
            "RequiresApproval",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
        )

        client, _, _ = buildDynClient(
            makeGetHandler(namespaceResponse=[subscription]),
            makeGetHandler(namespaceResponse=[pending]),
        )

        approvals = getPendingInstallPlans(client, "test-namespace")

        assert len(approvals) == 1
        assert approvals[0]["subscription"] == "test-operator-sub"
        assert approvals[0]["package"] == "test-operator"

    def test_aggregates_across_namespaces_and_caches_subscription_lists(self):
        subscriptionA = makeSubscription("sub-a", "namespace-a", "package-a", installedCSV="package-a.v1.0.0")
        subscriptionB = makeSubscription("sub-b", "namespace-b", "package-b", installedCSV="package-b.v1.0.0")
        planA = makeInstallPlan("plan-a", "namespace-a", ["package-a.v2.0.0"], "RequiresApproval", ownerRefs=[makeOwnerRef("Subscription", "sub-a")])
        planB1 = makeInstallPlan("plan-b1", "namespace-b", ["package-b.v2.0.0"], "RequiresApproval", ownerRefs=[makeOwnerRef("Subscription", "sub-b")])
        planB2 = makeInstallPlan("plan-b2", "namespace-b", ["package-b.v3.0.0"], "RequiresApproval", ownerRefs=[makeOwnerRef("Subscription", "sub-b")])
        planBComplete = makeInstallPlan("plan-b-complete", "namespace-b", ["package-b.v1.0.0"], "Complete")

        subscriptionCalls = []

        def subscriptionHandler(*args, **kwargs):
            subscriptionCalls.append(kwargs.get("namespace"))
            byNamespace = {"namespace-a": [subscriptionA], "namespace-b": [subscriptionB]}
            return ResourceList(byNamespace.get(kwargs.get("namespace"), []))

        def installPlanHandler(*args, **kwargs):
            return ResourceList([planA, planBComplete, planB1, planB2])

        client, _, _ = buildDynClient(subscriptionHandler, installPlanHandler)

        approvals = getPendingInstallPlans(client)

        assert {info["installPlan"] for info in approvals} == {"plan-a", "plan-b1", "plan-b2"}
        assert {info["namespace"] for info in approvals} == {"namespace-a", "namespace-b"}
        assert {info["subscription"] for info in approvals} == {"sub-a", "sub-b"}
        # One Subscription list per namespace despite two pending InstallPlans in namespace-b
        assert sorted(subscriptionCalls) == ["namespace-a", "namespace-b"]


class TestGetPendingInstallPlan:
    """Tests for getPendingInstallPlan."""

    def test_found_via_label_selector(self):
        subscription = makeSubscription("test-operator", "test-namespace", "test-operator", installedCSV="test-operator.v1.0.0")
        pending = makeInstallPlan(
            "install-plan-pending",
            "test-namespace",
            ["test-operator.v2.0.0"],
            "RequiresApproval",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
        )

        client, _, _ = buildDynClient(
            makeGetHandler(labelResponse=[subscription]),
            makeGetHandler(labelResponse=[pending]),
        )

        approvalInfo = getPendingInstallPlan(client, "test-namespace", "test-operator")

        assert approvalInfo is not None
        assert approvalInfo["installPlan"] == "install-plan-pending"
        assert approvalInfo["subscription"] == "test-operator"
        assert approvalInfo["currentCSV"] == "test-operator.v1.0.0"
        assert approvalInfo["targetCSV"] == "test-operator.v2.0.0"

    def test_found_via_owner_reference_fallback(self):
        # The label selector only returns a Complete InstallPlan; the pending
        # one is owned by the Subscription and found via the namespace listing
        subscription = makeSubscription("test-operator", "test-namespace", "test-operator")
        completeViaLabel = makeInstallPlan(
            "install-plan-complete",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "Complete",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
        )
        pendingOwned = makeInstallPlan(
            "install-plan-owned",
            "test-namespace",
            ["test-operator.v2.0.0"],
            "RequiresApproval",
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )

        client, _, _ = buildDynClient(
            makeGetHandler(labelResponse=[subscription]),
            makeGetHandler(labelResponse=[completeViaLabel], namespaceResponse=[pendingOwned, completeViaLabel]),
        )

        approvalInfo = getPendingInstallPlan(client, "test-namespace", "test-operator")

        assert approvalInfo is not None
        assert approvalInfo["installPlan"] == "install-plan-owned"

    def test_returns_none_when_no_subscription(self):
        client, _, _ = buildDynClient(makeGetHandler(labelResponse=[]), makeGetHandler())

        assert getPendingInstallPlan(client, "test-namespace", "test-operator") is None

    def test_returns_none_when_nothing_pending(self):
        subscription = makeSubscription("test-operator", "test-namespace", "test-operator")
        complete = makeInstallPlan(
            "install-plan-complete",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "Complete",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
        )

        client, _, _ = buildDynClient(
            makeGetHandler(labelResponse=[subscription]),
            makeGetHandler(labelResponse=[complete], namespaceResponse=[complete]),
        )

        assert getPendingInstallPlan(client, "test-namespace", "test-operator") is None


class TestApproveInstallPlan:
    """Tests for approveInstallPlan."""

    def test_approves_via_merge_patch(self):
        pending = makeInstallPlan("install-plan-1", "test-namespace", ["test-operator.v1.0.0"], "RequiresApproval", approved=False)
        client, _, installPlanAPI = buildDynClient(makeGetHandler(), makeGetHandler(nameResponse=pending))

        result = approveInstallPlan(client, "test-namespace", "install-plan-1")

        assert result is installPlanAPI.patch.return_value
        assert pending.spec.approved is True
        installPlanAPI.patch.assert_called_once()
        _, kwargs = installPlanAPI.patch.call_args
        assert kwargs["name"] == "install-plan-1"
        assert kwargs["namespace"] == "test-namespace"
        assert kwargs["content_type"] == "application/merge-patch+json"

    def test_noop_when_already_approved(self):
        approved = makeInstallPlan("install-plan-1", "test-namespace", ["test-operator.v1.0.0"], "RequiresApproval", approved=True)
        client, _, installPlanAPI = buildDynClient(makeGetHandler(), makeGetHandler(nameResponse=approved))

        result = approveInstallPlan(client, "test-namespace", "install-plan-1")

        assert result is approved
        installPlanAPI.patch.assert_not_called()

    def test_noop_when_complete(self):
        complete = makeInstallPlan("install-plan-1", "test-namespace", ["test-operator.v1.0.0"], "Complete")
        client, _, installPlanAPI = buildDynClient(makeGetHandler(), makeGetHandler(nameResponse=complete))

        result = approveInstallPlan(client, "test-namespace", "install-plan-1")

        assert result is complete
        installPlanAPI.patch.assert_not_called()

    def test_raises_when_failed(self):
        failed = makeInstallPlan(
            "install-plan-1",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "Failed",
            conditions=[{"type": "InstallationFailed", "message": "component failed to install"}],
        )
        client, _, installPlanAPI = buildDynClient(makeGetHandler(), makeGetHandler(nameResponse=failed))

        with pytest.raises(OLMException) as excinfo:
            approveInstallPlan(client, "test-namespace", "install-plan-1")

        assert "has failed and cannot be approved" in str(excinfo.value)
        assert "component failed to install" in str(excinfo.value)
        installPlanAPI.patch.assert_not_called()


class TestWaitForInstallPlanComplete:
    """Tests for waitForInstallPlanComplete."""

    def test_waits_until_complete(self):
        pending = makeInstallPlan("install-plan-1", "test-namespace", ["test-operator.v1.0.0"], "RequiresApproval")
        complete = makeInstallPlan("install-plan-1", "test-namespace", ["test-operator.v1.0.0"], "Complete")
        client, _, _ = buildDynClient(makeGetHandler(), makeGetHandler(nameResponse=ResponseSequence([pending, complete])))

        with patch("mas.devops.olm.sleep"):
            result = waitForInstallPlanComplete(client, "test-namespace", "install-plan-1", timeout=60, pollInterval=1)

        assert result is complete

    def test_raises_when_failed(self):
        failed = makeInstallPlan(
            "install-plan-1",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "Failed",
            conditions=[{"type": "InstallationFailed", "message": "component failed to install"}],
        )
        client, _, _ = buildDynClient(makeGetHandler(), makeGetHandler(nameResponse=failed))

        with pytest.raises(OLMException) as excinfo:
            waitForInstallPlanComplete(client, "test-namespace", "install-plan-1")

        assert "has failed" in str(excinfo.value)
        assert "component failed to install" in str(excinfo.value)

    def test_raises_olm_timeout_error_on_expiry(self):
        installing = makeInstallPlan("install-plan-1", "test-namespace", ["test-operator.v1.0.0"], "Installing")
        client, _, _ = buildDynClient(makeGetHandler(), makeGetHandler(nameResponse=installing))

        with patch("mas.devops.olm.sleep"), patch("mas.devops.olm.time", side_effect=[0, 500]):
            with pytest.raises(OLMTimeoutError):
                waitForInstallPlanComplete(client, "test-namespace", "install-plan-1", timeout=300, pollInterval=1)


class TestWaitForSubscriptionStable:
    """Tests for waitForSubscriptionStable."""

    def test_returns_when_at_latest_known(self):
        subscription = makeSubscription("test-operator", "test-namespace", "test-operator", state="AtLatestKnown")
        client, _, _ = buildDynClient(
            makeGetHandler(labelResponse=[subscription], nameResponse=subscription),
            makeGetHandler(),
        )

        result = waitForSubscriptionStable(client, "test-namespace", "test-operator", timeout=60)

        assert result is subscription

    def test_returns_when_upgrade_pending_matches_target_csv(self):
        subscription = makeSubscription("test-operator", "test-namespace", "test-operator", state="UpgradePending", installedCSV="test-operator.v1.0.0")
        client, _, _ = buildDynClient(
            makeGetHandler(labelResponse=[subscription], nameResponse=subscription),
            makeGetHandler(),
        )

        result = waitForSubscriptionStable(client, "test-namespace", "test-operator", timeout=60, targetCSV="test-operator.v1.0.0")

        assert result is subscription

    def test_raises_olm_timeout_error_on_expiry(self):
        subscription = makeSubscription("test-operator", "test-namespace", "test-operator", state="UpgradePending", installedCSV="test-operator.v0.9.0")
        client, _, _ = buildDynClient(
            makeGetHandler(labelResponse=[subscription], nameResponse=subscription),
            makeGetHandler(),
        )

        with patch("mas.devops.olm.sleep"), patch("mas.devops.olm.time", side_effect=[0, 500]):
            with pytest.raises(OLMTimeoutError):
                waitForSubscriptionStable(client, "test-namespace", "test-operator", timeout=300, targetCSV="test-operator.v1.0.0")

    def test_raises_when_no_subscription(self):
        client, _, _ = buildDynClient(makeGetHandler(labelResponse=[]), makeGetHandler())

        with pytest.raises(OLMException, match="No subscription found"):
            waitForSubscriptionStable(client, "test-namespace", "test-operator")


class TestGetSubscriptionInstallPlanRefs:
    """Tests for getSubscriptionInstallPlanRefs."""

    def test_maps_names_to_ref_names(self):
        fresh = makeSubscription("fresh-operator", "test-namespace", "fresh-operator")
        settled = makeSubscription("settled-operator", "test-namespace", "settled-operator", installPlanRef="install-plan-1")
        client, _, _ = buildDynClient(makeGetHandler(namespaceResponse=[fresh, settled]), makeGetHandler())

        assert getSubscriptionInstallPlanRefs(client, "test-namespace") == {
            "fresh-operator": None,
            "settled-operator": "install-plan-1",
        }

    def test_empty_namespace_returns_empty_map(self):
        client, _, _ = buildDynClient(makeGetHandler(namespaceResponse=[]), makeGetHandler())

        assert getSubscriptionInstallPlanRefs(client, "test-namespace") == {}


class TestWaitForSubscriptionInstallPlans:
    """Tests for waitForSubscriptionInstallPlans."""

    def test_returns_immediately_when_all_refs_present(self):
        settled = makeSubscription("test-operator", "test-namespace", "test-operator", installPlanRef="install-plan-1")
        client, subscriptionAPI, _ = buildDynClient(makeGetHandler(namespaceResponse=[settled]), makeGetHandler())

        with patch("mas.devops.olm.sleep") as mockSleep:
            waitForSubscriptionInstallPlans(client, "test-namespace", timeout=60, pollInterval=1)

        mockSleep.assert_not_called()
        assert subscriptionAPI.get.call_count == 1

    def test_waits_until_refs_appear(self):
        fresh = makeSubscription("test-operator", "test-namespace", "test-operator")
        settled = makeSubscription("test-operator", "test-namespace", "test-operator", installPlanRef="install-plan-1")
        client, subscriptionAPI, _ = buildDynClient(
            # Each pop of the sequence is the full listing for that poll
            # (fresh on the first poll, settled from the second on)
            makeGetHandler(namespaceResponse=ResponseSequence([[fresh], [settled]])),
            makeGetHandler(),
        )

        with patch("mas.devops.olm.sleep") as mockSleep:
            waitForSubscriptionInstallPlans(client, "test-namespace", timeout=60, pollInterval=1)

        assert subscriptionAPI.get.call_count == 2
        mockSleep.assert_called_once()

    def test_raises_olm_timeout_error_naming_unresolved_subscriptions(self):
        fresh = makeSubscription("test-operator", "test-namespace", "test-operator")
        client, _, _ = buildDynClient(makeGetHandler(namespaceResponse=[fresh]), makeGetHandler())

        with patch("mas.devops.olm.sleep"), patch("mas.devops.olm.time", side_effect=[0, 700]):
            with pytest.raises(OLMTimeoutError) as excinfo:
                waitForSubscriptionInstallPlans(client, "test-namespace", timeout=600, pollInterval=1)

        message = str(excinfo.value)
        assert "still without an installPlanRef: test-operator" in message
        assert "oc get subscription -n test-namespace" in message


class TestWaitForSubscriptionResolution:
    """Tests for waitForSubscriptionResolution."""

    def test_settles_after_quiet_polls(self):
        settled = makeSubscription(
            "test-operator",
            "test-namespace",
            "test-operator",
            state="AtLatestKnown",
            installPlanRef="install-plan-1",
            installPlanGeneration=3,
        )
        client, subscriptionAPI, _ = buildDynClient(makeGetHandler(namespaceResponse=[settled]), makeGetHandler())

        with patch("mas.devops.olm.sleep") as mockSleep:
            waitForSubscriptionResolution(client, "test-namespace", timeout=60, pollInterval=1, quietPolls=4)

        # Four identical snapshots conclude the settle
        assert subscriptionAPI.get.call_count == 4
        assert mockSleep.call_count == 3

    def test_keeps_polling_while_statuses_churn(self):
        calls = []

        def churningThenStableHandler(*args, **kwargs):
            if "namespace" in kwargs:
                generation = len(calls)
                calls.append(1)
                # The first two polls churn (OLM resolving a channel change:
                # installPlanGeneration bumps and the ref is replaced), then
                # the status is stable
                if generation < 2:
                    subscription = makeSubscription(
                        "test-operator",
                        "test-namespace",
                        "test-operator",
                        state="UpgradePending",
                        installPlanRef=f"install-plan-{generation}",
                        installPlanGeneration=generation,
                    )
                else:
                    subscription = makeSubscription(
                        "test-operator",
                        "test-namespace",
                        "test-operator",
                        state="UpgradePending",
                        installPlanRef="install-plan-final",
                        installPlanGeneration=2,
                    )
                return ResourceList([subscription])
            return ResourceList([])

        client, subscriptionAPI, _ = buildDynClient(churningThenStableHandler, makeGetHandler())

        with patch("mas.devops.olm.sleep"):
            waitForSubscriptionResolution(client, "test-namespace", timeout=60, pollInterval=1, quietPolls=4)

        # 2 churning polls + 4 identical polls
        assert subscriptionAPI.get.call_count == 6

    def test_timeout_mid_churn_is_not_fatal(self, caplog):
        calls = []

        def perpetualChurnHandler(*args, **kwargs):
            if "namespace" in kwargs:
                generation = len(calls)
                calls.append(1)
                subscription = makeSubscription(
                    "test-operator",
                    "test-namespace",
                    "test-operator",
                    state="Installing",
                    installPlanGeneration=generation,
                )
                return ResourceList([subscription])
            return ResourceList([])

        client, _, _ = buildDynClient(perpetualChurnHandler, makeGetHandler())

        with patch("mas.devops.olm.sleep"), patch("mas.devops.olm.time", side_effect=[0, 700]):
            with caplog.at_level(logging.WARNING, logger="mas.devops.olm"):
                result = waitForSubscriptionResolution(client, "test-namespace", timeout=600, pollInterval=1, quietPolls=4)

        # A still-churning cluster proceeds with whatever is visible rather
        # than failing: "nothing more is coming" cannot be disproved
        assert result is not None
        assert "was still changing after 600s" in caplog.text

    def test_cluster_wide_scope_lists_all_namespaces(self):
        settled = makeSubscription("test-operator", "other-namespace", "test-operator", state="AtLatestKnown")
        client, subscriptionAPI, _ = buildDynClient(makeGetHandler(allResponse=[settled]), makeGetHandler())

        with patch("mas.devops.olm.sleep"):
            waitForSubscriptionResolution(client, namespace=None, timeout=60, pollInterval=1, quietPolls=2)

        # The kwargs-free listing is the cluster-wide query
        assert all("namespace" not in call.kwargs for call in subscriptionAPI.get.call_args_list)

    def test_ignores_fields_that_churn_for_unrelated_reasons(self):
        """catalogHealth-style noise is not part of the resolution fingerprint.

        Simulated by returning the same resolution fingerprint on every poll
        from a fresh (thus attribute-different) Subscription object: only the
        fingerprinted fields may influence stability.
        """
        snapshots = [
            makeSubscription(
                "test-operator",
                "test-namespace",
                "test-operator",
                state="AtLatestKnown",
                installPlanRef="install-plan-1",
                installPlanGeneration=3,
                installedCSV="csv-1",
                currentCSV="csv-1",
            )
            for _ in range(2)
        ]
        client, subscriptionAPI, _ = buildDynClient(
            # Each poll returns a fresh Subscription object with the same
            # fingerprinted field values (one listing per sequence pop)
            makeGetHandler(namespaceResponse=ResponseSequence([[snapshots[0]], [snapshots[1]]])),
            makeGetHandler(),
        )

        with patch("mas.devops.olm.sleep"):
            waitForSubscriptionResolution(client, "test-namespace", timeout=60, pollInterval=1, quietPolls=2)

        assert subscriptionAPI.get.call_count == 2


class TestApplySubscriptionValidation:
    """Tests for applySubscription parameter validation (no cluster interaction)."""

    def test_manual_without_starting_csv_raises_without_opt_in(self):
        with pytest.raises(OLMException, match="startingCSV must be provided"):
            applySubscription(
                Mock(),
                "test-namespace",
                "test-operator",
                packageChannel="stable",
                catalogSource="test-catalog",
                installPlanApproval="Manual",
            )

    def test_invalid_on_approval_required_raises(self):
        with pytest.raises(OLMException, match="onApprovalRequired must be"):
            applySubscription(
                Mock(),
                "test-namespace",
                "test-operator",
                packageChannel="stable",
                catalogSource="test-catalog",
                installPlanApproval="Manual",
                onApprovalRequired="bogus",
            )

    def test_auto_approve_initial_install_requires_manual(self):
        with pytest.raises(OLMException, match="autoApproveInitialInstall is only valid"):
            applySubscription(
                Mock(),
                "test-namespace",
                "test-operator",
                packageChannel="stable",
                catalogSource="test-catalog",
                installPlanApproval="Automatic",
                autoApproveInitialInstall=True,
            )

    def test_mixed_namespace_tolerated_by_new_style_callers(self, caplog):
        # A dependency subscription in the namespace uses the default Automatic
        # mode: applying a Manual subscription must proceed with a warning, not
        # fail -- OLM auto-creates such subscriptions in real Manual namespaces
        # (for example ibm-truststore-mgr alongside ibm-sls)
        other = makeSubscription("other-operator", "test-namespace", "other-operator", approval=None)
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v1.0.0"
        )
        pendingPlan = makeInstallPlan(
            "install-plan-1",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "RequiresApproval",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        client, _, installPlanAPI = buildDynClient(
            makeGetHandler(labelResponse=[subscription], nameResponse=subscription, namespaceResponse=[other]),
            makeGetHandler(labelResponse=[pendingPlan], nameResponse=pendingPlan),
        )

        with applySubscriptionIsolation():
            with caplog.at_level(logging.WARNING, logger="mas.devops.olm"):
                result = applySubscription(
                    client,
                    "test-namespace",
                    "test-operator",
                    packageChannel="stable",
                    catalogSource="test-catalog",
                    installPlanApproval="Manual",
                    onApprovalRequired="return",
                )

        assert isinstance(result, tuple)
        assert result[1]["installPlan"] == "install-plan-1"
        installPlanAPI.patch.assert_not_called()
        assert "mix of approval modes" in caplog.text
        assert "other-operator" in caplog.text


class TestApplySubscriptionApprovalHandling:
    """Tests for the opt-in approval handling modes of applySubscription."""

    def test_point_a_release_returns_subscription_and_approval_info(self):
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v1.0.0"
        )
        pendingPlan = makeInstallPlan(
            "install-plan-1",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "RequiresApproval",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        client, _, installPlanAPI = buildDynClient(
            makeGetHandler(labelResponse=[subscription], nameResponse=subscription, namespaceResponse=[]),
            makeGetHandler(labelResponse=[pendingPlan], nameResponse=pendingPlan),
        )

        with applySubscriptionIsolation():
            result = applySubscription(
                client,
                "test-namespace",
                "test-operator",
                packageChannel="stable",
                catalogSource="test-catalog",
                installPlanApproval="Manual",
                onApprovalRequired="return",
            )

        assert isinstance(result, tuple)
        subscriptionResult, approvalInfo = result
        assert subscriptionResult is subscription
        assert approvalInfo["installPlan"] == "install-plan-1"
        assert approvalInfo["subscription"] == "test-operator"
        assert approvalInfo["package"] == "test-operator"
        assert approvalInfo["csvNames"] == ["test-operator.v1.0.0"]
        assert approvalInfo["currentCSV"] == "test-operator.v1.0.0"
        assert approvalInfo["targetCSV"] == "test-operator.v1.0.0"
        installPlanAPI.patch.assert_not_called()

    def test_auto_approve_disabled_releases_without_patching(self):
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v1.0.0"
        )
        pendingPlan = makeInstallPlan(
            "install-plan-1",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "RequiresApproval",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        client, _, installPlanAPI = buildDynClient(
            makeGetHandler(labelResponse=[subscription], nameResponse=subscription, namespaceResponse=[]),
            makeGetHandler(labelResponse=[pendingPlan], nameResponse=pendingPlan),
        )

        with applySubscriptionIsolation():
            result = applySubscription(
                client,
                "test-namespace",
                "test-operator",
                packageChannel="stable",
                catalogSource="test-catalog",
                installPlanApproval="Manual",
                startingCSV="test-operator.v1.0.0",
                autoApproveInitialInstall=False,
                onApprovalRequired="return",
            )

        assert isinstance(result, tuple)
        assert result[1]["installPlan"] == "install-plan-1"
        installPlanAPI.patch.assert_not_called()

    def test_own_subscription_excluded_from_consistency_check(self, caplog):
        # The namespace listing contains only the subscription being applied
        # (in a different mode): it must be excluded from the consistency check
        own = makeSubscription("test-operator", "test-namespace", "test-operator", approval=None)
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v1.0.0"
        )
        pendingPlan = makeInstallPlan(
            "install-plan-1",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "RequiresApproval",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        client, _, _ = buildDynClient(
            makeGetHandler(labelResponse=[subscription], nameResponse=subscription, namespaceResponse=[own]),
            makeGetHandler(labelResponse=[pendingPlan], nameResponse=pendingPlan),
        )

        with applySubscriptionIsolation():
            with caplog.at_level(logging.WARNING, logger="mas.devops.olm"):
                result = applySubscription(
                    client,
                    "test-namespace",
                    "test-operator",
                    packageChannel="stable",
                    catalogSource="test-catalog",
                    installPlanApproval="Manual",
                    onApprovalRequired="return",
                )

        assert isinstance(result, tuple)
        # The only other subscription in the namespace is the one being applied,
        # so no mixed-mode warning may be logged
        assert "mix of approval modes" not in caplog.text

    def test_callback_release_invokes_callback_with_approval_info(self):
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v1.0.0"
        )
        pendingPlan = makeInstallPlan(
            "install-plan-1",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "RequiresApproval",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        callback = Mock(return_value=False)
        client, _, _ = buildDynClient(
            makeGetHandler(labelResponse=[subscription], nameResponse=subscription, namespaceResponse=[]),
            makeGetHandler(labelResponse=[pendingPlan], nameResponse=pendingPlan),
        )

        with applySubscriptionIsolation():
            result = applySubscription(
                client,
                "test-namespace",
                "test-operator",
                packageChannel="stable",
                catalogSource="test-catalog",
                installPlanApproval="Manual",
                onApprovalRequired=callback,
            )

        assert isinstance(result, tuple)
        callback.assert_called_once()
        approvalInfo = callback.call_args[0][0]
        assert approvalInfo["installPlan"] == "install-plan-1"
        assert approvalInfo["package"] == "test-operator"

    def test_callback_continue_waits_until_approved_out_of_band(self):
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="AtLatestKnown", installedCSV="test-operator.v1.0.0"
        )
        pendingPlan = makeInstallPlan(
            "install-plan-1",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "RequiresApproval",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        completePlan = makeInstallPlan(
            "install-plan-1",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "Complete",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        callback = Mock(return_value=True)
        client, _, _ = buildDynClient(
            makeGetHandler(labelResponse=[subscription], nameResponse=subscription, namespaceResponse=[]),
            makeGetHandler(labelResponse=[pendingPlan], nameResponse=ResponseSequence([pendingPlan, completePlan])),
        )

        with applySubscriptionIsolation():
            result = applySubscription(
                client,
                "test-namespace",
                "test-operator",
                packageChannel="stable",
                catalogSource="test-catalog",
                installPlanApproval="Manual",
                onApprovalRequired=callback,
            )

        assert not isinstance(result, tuple)
        assert result is subscription
        callback.assert_called_once()

    def test_point_b_release_returns_pending_upgrade_plan(self):
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v0.9.0"
        )
        completePlan = makeInstallPlan(
            "install-plan-initial",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "Complete",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        pendingUpgradePlan = makeInstallPlan(
            "install-plan-upgrade",
            "test-namespace",
            ["test-operator.v2.0.0"],
            "RequiresApproval",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        client, _, installPlanAPI = buildDynClient(
            makeGetHandler(labelResponse=[subscription], nameResponse=subscription, namespaceResponse=[]),
            makeGetHandler(labelResponse=[completePlan, pendingUpgradePlan], nameResponse=completePlan),
        )

        with applySubscriptionIsolation():
            result = applySubscription(
                client,
                "test-namespace",
                "test-operator",
                packageChannel="stable",
                catalogSource="test-catalog",
                installPlanApproval="Manual",
                startingCSV="test-operator.v1.0.0",
                onApprovalRequired="return",
            )

        assert isinstance(result, tuple)
        subscriptionResult, approvalInfo = result
        assert subscriptionResult is subscription
        assert approvalInfo["installPlan"] == "install-plan-upgrade"
        assert approvalInfo["currentCSV"] == "test-operator.v0.9.0"
        assert approvalInfo["targetCSV"] == "test-operator.v2.0.0"
        installPlanAPI.patch.assert_not_called()

    def test_legacy_auto_approve_behavior_unchanged(self):
        # Default parameters: the initial InstallPlan to startingCSV is
        # auto-approved once and the subscription is returned when its
        # installedCSV reaches startingCSV. The namespace also contains an
        # Automatic-mode subscription: legacy callers must not be affected by
        # the namespace consistency validation
        other = makeSubscription("other-operator", "test-namespace", "other-operator", approval=None)
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v1.0.0"
        )
        pendingPlan = makeInstallPlan(
            "install-plan-1",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "RequiresApproval",
            approved=False,
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        completePlan = makeInstallPlan(
            "install-plan-1",
            "test-namespace",
            ["test-operator.v1.0.0"],
            "Complete",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        # Two pendingPlan entries: one consumed by the wait loop and one by
        # approveInstallPlan's internal fetch
        client, _, installPlanAPI = buildDynClient(
            makeGetHandler(labelResponse=[subscription], nameResponse=subscription, namespaceResponse=[other]),
            makeGetHandler(labelResponse=[pendingPlan], nameResponse=ResponseSequence([pendingPlan, pendingPlan, completePlan])),
        )

        with applySubscriptionIsolation():
            result = applySubscription(
                client,
                "test-namespace",
                "test-operator",
                packageChannel="stable",
                catalogSource="test-catalog",
                installPlanApproval="Manual",
                startingCSV="test-operator.v1.0.0",
            )

        assert not isinstance(result, tuple)
        assert result is subscription
        assert pendingPlan.spec.approved is True
        installPlanAPI.patch.assert_called_once()
        _, kwargs = installPlanAPI.patch.call_args
        assert kwargs["content_type"] == "application/merge-patch+json"


class TestGetNamespaceApprovalStatus:
    """Tests for getNamespaceApprovalStatus."""

    def test_empty_namespace(self):
        client, _, _ = buildDynClient(makeGetHandler(namespaceResponse=[]), makeGetHandler(namespaceResponse=[]))

        assert getNamespaceApprovalStatus(client, "test-namespace") == {
            "namespace": "test-namespace",
            "approvalMode": None,
            "pendingApprovals": [],
            "blocking": False,
        }

    def test_manual_subscription_without_pending_plan(self):
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="AtLatestKnown", installedCSV="test-operator.v1.0.0"
        )
        client, _, _ = buildDynClient(makeGetHandler(namespaceResponse=[subscription]), makeGetHandler(namespaceResponse=[]))

        status = getNamespaceApprovalStatus(client, "test-namespace")

        assert status == {
            "namespace": "test-namespace",
            "approvalMode": "Manual",
            "pendingApprovals": [],
            "blocking": False,
        }

    def test_pending_approvals_enriched_and_blocking(self):
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v1.0.0"
        )
        pending = makeInstallPlan(
            "install-plan-pending",
            "test-namespace",
            ["test-operator.v1.0.0", "test-operator.v2.0.0"],
            "RequiresApproval",
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        complete = makeInstallPlan("install-plan-complete", "test-namespace", ["test-operator.v0.9.0"], "Complete")
        installing = makeInstallPlan("install-plan-installing", "test-namespace", ["test-operator.v3.0.0"], "Installing")

        client, _, _ = buildDynClient(
            makeGetHandler(namespaceResponse=[subscription]),
            makeGetHandler(namespaceResponse=[pending, complete, installing]),
        )

        status = getNamespaceApprovalStatus(client, "test-namespace")

        assert status == {
            "namespace": "test-namespace",
            "approvalMode": "Manual",
            "pendingApprovals": [
                {
                    "installPlan": "install-plan-pending",
                    "namespace": "test-namespace",
                    "subscription": "test-operator",
                    "package": "test-operator",
                    "csvNames": ["test-operator.v1.0.0", "test-operator.v2.0.0"],
                    "currentCSV": "test-operator.v1.0.0",
                    "targetCSV": "test-operator.v2.0.0",
                    "created": "2026-11-15T10:00:00Z",
                }
            ],
            "blocking": True,
        }

    def test_pending_approval_resolved_via_label_fallback(self):
        subscription = makeSubscription("test-operator-sub", "test-namespace", "test-operator", approval="Manual", installedCSV="test-operator.v1.0.0")
        pending = makeInstallPlan(
            "install-plan-pending",
            "test-namespace",
            ["test-operator.v2.0.0"],
            "RequiresApproval",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
        )

        client, _, _ = buildDynClient(
            makeGetHandler(namespaceResponse=[subscription]),
            makeGetHandler(namespaceResponse=[pending]),
        )

        status = getNamespaceApprovalStatus(client, "test-namespace")

        assert status["pendingApprovals"][0]["subscription"] == "test-operator-sub"
        assert status["pendingApprovals"][0]["package"] == "test-operator"
        assert status["blocking"] is True

    def test_mixed_modes_reported_not_raised(self):
        # OLM auto-creates dependency subscriptions that can legitimately mix
        # modes in one namespace: the status function reports the mix instead
        # of raising (getSubscriptionApprovalMode remains the strict accessor)
        manual = makeSubscription("manual-operator", "test-namespace", "manual-operator", approval="Manual")
        automatic = makeSubscription("automatic-operator", "test-namespace", "automatic-operator", approval=None)
        client, _, _ = buildDynClient(makeGetHandler(namespaceResponse=[manual, automatic]), makeGetHandler(namespaceResponse=[]))

        status = getNamespaceApprovalStatus(client, "test-namespace")

        assert status["approvalMode"] == "Mixed"
        assert status["blocking"] is False

    def test_pending_approvals_share_the_apply_subscription_release_contract(self):
        # The pendingApprovals entries must be the same shape as the approval
        # info dicts applySubscription returns in its release path (Phase 1's
        # test_point_a_release_returns_subscription_and_approval_info pins the
        # same keys on that side)
        subscription = makeSubscription("test-operator", "test-namespace", "test-operator", approval="Manual", installedCSV="test-operator.v1.0.0")
        pending = makeInstallPlan(
            "install-plan-pending",
            "test-namespace",
            ["test-operator.v2.0.0"],
            "RequiresApproval",
            ownerRefs=[makeOwnerRef("Subscription", "test-operator")],
        )
        client, _, _ = buildDynClient(
            makeGetHandler(namespaceResponse=[subscription]),
            makeGetHandler(namespaceResponse=[pending]),
        )

        status = getNamespaceApprovalStatus(client, "test-namespace")

        assert set(status["pendingApprovals"][0]) == {
            "installPlan",
            "namespace",
            "subscription",
            "package",
            "csvNames",
            "currentCSV",
            "targetCSV",
            "created",
        }


class TestIsApprovalRequired:
    """Tests for isApprovalRequired."""

    def test_true_when_any_plan_requires_approval(self):
        pending = makeInstallPlan("install-plan-pending", "test-namespace", ["test-operator.v2.0.0"], "RequiresApproval")
        complete = makeInstallPlan("install-plan-complete", "test-namespace", ["test-operator.v1.0.0"], "Complete")
        client, _, _ = buildDynClient(makeGetHandler(), makeGetHandler(namespaceResponse=[complete, pending]))

        assert isApprovalRequired(client, "test-namespace") is True

    def test_false_when_nothing_requires_approval(self):
        complete = makeInstallPlan("install-plan-complete", "test-namespace", ["test-operator.v1.0.0"], "Complete")
        installing = makeInstallPlan("install-plan-installing", "test-namespace", ["test-operator.v2.0.0"], "Installing")
        client, _, _ = buildDynClient(makeGetHandler(), makeGetHandler(namespaceResponse=[complete, installing]))

        assert isApprovalRequired(client, "test-namespace") is False

    def test_false_when_no_install_plans(self):
        client, _, _ = buildDynClient(makeGetHandler(), makeGetHandler(namespaceResponse=[]))

        assert isApprovalRequired(client, "test-namespace") is False


class TestWaitForNamespaceApprovals:
    """Tests for waitForNamespaceApprovals."""

    def test_returns_immediately_when_nothing_pending(self):
        subscription = makeSubscription("test-operator", "test-namespace", "test-operator", approval="Manual", state="AtLatestKnown")
        onPending = Mock()
        client, _, _ = buildDynClient(
            makeGetHandler(namespaceResponse=[subscription]),
            makeGetHandler(namespaceResponse=[]),
        )

        with patch("mas.devops.olm.sleep"):
            status = waitForNamespaceApprovals(client, "test-namespace", timeout=60, onPending=onPending)

        assert status["blocking"] is False
        onPending.assert_not_called()

    def test_returns_when_approval_resolved_out_of_band(self):
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v1.0.0"
        )
        pending = makeInstallPlan(
            "install-plan-pending", "test-namespace", ["test-operator.v2.0.0"], "RequiresApproval", ownerRefs=[makeOwnerRef("Subscription", "test-operator")]
        )
        client, _, _ = buildDynClient(
            makeGetHandler(namespaceResponse=[subscription]),
            makeGetHandler(namespaceResponse=ResponseSequence([[pending], []])),
        )

        with patch("mas.devops.olm.sleep"):
            status = waitForNamespaceApprovals(client, "test-namespace", timeout=60)

        assert status["blocking"] is False
        assert status["pendingApprovals"] == []

    def test_on_pending_invoked_every_poll_with_status_and_counter(self):
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v1.0.0"
        )
        pending = makeInstallPlan(
            "install-plan-pending", "test-namespace", ["test-operator.v2.0.0"], "RequiresApproval", ownerRefs=[makeOwnerRef("Subscription", "test-operator")]
        )
        onPending = Mock(return_value=None)
        client, _, _ = buildDynClient(
            makeGetHandler(namespaceResponse=[subscription]),
            makeGetHandler(namespaceResponse=ResponseSequence([[pending], [pending], []])),
        )

        with patch("mas.devops.olm.sleep"):
            status = waitForNamespaceApprovals(client, "test-namespace", timeout=60, onPending=onPending)

        assert status["blocking"] is False
        assert onPending.call_count == 2
        firstStatus, firstCount = onPending.call_args_list[0][0]
        secondStatus, secondCount = onPending.call_args_list[1][0]
        assert firstCount == 1
        assert secondCount == 2
        assert firstStatus["blocking"] is True
        assert firstStatus["pendingApprovals"][0]["installPlan"] == "install-plan-pending"

    def test_on_pending_returning_false_aborts_with_blocking_status(self):
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v1.0.0"
        )
        pending = makeInstallPlan(
            "install-plan-pending", "test-namespace", ["test-operator.v2.0.0"], "RequiresApproval", ownerRefs=[makeOwnerRef("Subscription", "test-operator")]
        )
        onPending = Mock(return_value=False)
        client, _, _ = buildDynClient(
            makeGetHandler(namespaceResponse=[subscription]),
            makeGetHandler(namespaceResponse=[pending]),
        )

        with patch("mas.devops.olm.sleep"):
            status = waitForNamespaceApprovals(client, "test-namespace", timeout=60, onPending=onPending)

        assert status["blocking"] is True
        assert status["pendingApprovals"][0]["installPlan"] == "install-plan-pending"
        onPending.assert_called_once()

    def test_raises_olm_timeout_error_on_expiry(self):
        subscription = makeSubscription(
            "test-operator", "test-namespace", "test-operator", approval="Manual", state="UpgradePending", installedCSV="test-operator.v1.0.0"
        )
        pending = makeInstallPlan(
            "install-plan-pending", "test-namespace", ["test-operator.v2.0.0"], "RequiresApproval", ownerRefs=[makeOwnerRef("Subscription", "test-operator")]
        )
        client, _, _ = buildDynClient(
            makeGetHandler(namespaceResponse=[subscription]),
            makeGetHandler(namespaceResponse=[pending]),
        )

        with patch("mas.devops.olm.sleep"), patch("mas.devops.olm.time", side_effect=[0, 500]):
            with pytest.raises(OLMTimeoutError):
                waitForNamespaceApprovals(client, "test-namespace", timeout=300)


# Made with Bob
