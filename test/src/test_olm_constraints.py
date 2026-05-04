# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

"""
Unit tests for OLM ConstraintsNotSatisfiable parsing and recovery handling.
"""

import pytest
from unittest.mock import Mock, patch
from mas.devops import olm


class MockResource:
    """Mock Kubernetes resource object"""

    def __init__(self, name, labels=None, owner_refs=None, csv_names=None, phase="Complete"):
        self.metadata = Mock()
        self.metadata.name = name
        self.metadata.labels = labels or {}
        self.metadata.ownerReferences = owner_refs or []

        self.spec = Mock()
        self.spec.clusterServiceVersionNames = csv_names or []

        self.status = Mock()
        self.status.phase = phase


class MockResourceList:
    """Mock Kubernetes resource list"""

    def __init__(self, items):
        self.items = items
        self.status = Mock()


@pytest.fixture
def mock_dyn_client():
    client = Mock()
    return client


@pytest.fixture
def mock_env():
    env = Mock()
    template = Mock()
    template.render.return_value = """
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
    env.get_template.return_value = template
    return env


def _constraint_subscription(message, state="UpgradePending"):
    subscription = Mock()
    subscription.metadata.name = "test-operator"
    subscription.status = Mock()
    subscription.status.state = state

    condition = Mock()
    condition.type = "ResolutionFailed"
    condition.reason = "ConstraintsNotSatisfiable"
    condition.message = message

    subscription.status.conditions = [condition]
    return subscription


def test_get_subscription_constraint_message_returns_matching_message():
    message = (
        "clusterserviceversion test-operator.v1.0.0 exists and is not referenced by a subscription"
    )
    subscription = _constraint_subscription(message)

    assert olm._getSubscriptionConstraintMessage(subscription) == message


def test_parse_constraint_message_marketplace_cache():
    parsed = olm._parseConstraintMessage(
        "constraints not satisfiable: @existing/test-ns//test-operator.v2.0.0 and "
        "@existing/test-ns//test-operator.v1.0.0 originate from package test-operator, "
        "clusterserviceversion test-operator.v1.0.0 exists and is not referenced by a subscription, "
        "subscription test-operator exists, subscription test-operator requires "
        "@existing/test-ns//test-operator.v2.0.0"
    )

    assert parsed == {
        "scenario": "marketplace_cache",
        "existingCSV": "test-operator.v1.0.0",
        "requiredCSV": "test-operator.v2.0.0"
    }


def test_parse_constraint_message_catalog_behind():
    parsed = olm._parseConstraintMessage(
        "constraints not satisfiable: @existing/test-ns//test-operator.v1.0.0 and "
        "@existing/test-ns//test-operator.v2.0.0 originate from package test-operator, "
        "clusterserviceversion test-operator.v2.0.0 exists and is not referenced by a subscription, "
        "subscription test-operator exists, subscription test-operator requires "
        "@existing/test-ns//test-operator.v1.0.0"
    )

    assert parsed == {
        "scenario": "catalog_behind",
        "existingCSV": "test-operator.v2.0.0",
        "requiredCSV": "test-operator.v1.0.0"
    }


@patch('mas.devops.olm._deleteMarketplaceCatalogJobs')
@patch('mas.devops.olm._deleteInstallPlansBySelector')
@patch('mas.devops.olm.deleteSubscription')
@patch('mas.devops.olm.createNamespace')
@patch('mas.devops.olm.ensureOperatorGroupExists')
@patch('mas.devops.olm.getPackageManifest')
@patch('mas.devops.olm.sleep')
def test_marketplace_cache_recovery_reapplies_subscription(
    mock_sleep, mock_get_manifest, mock_ensure_og, mock_create_ns, mock_delete_subscription,
    mock_delete_installplans, mock_delete_jobs, mock_dyn_client, mock_env
):
    mock_get_manifest.return_value = Mock(
        status=Mock(defaultChannel="stable", catalogSource="test-catalog")
    )

    sub_api = Mock()
    healthy_subscription = Mock()
    healthy_subscription.metadata.name = "test-operator"
    healthy_subscription.status = Mock()
    healthy_subscription.status.state = "AtLatestKnown"
    healthy_subscription.status.conditions = []

    sub_api.get.side_effect = [
        MockResourceList([]),
        _constraint_subscription(
            "constraints not satisfiable: @existing/test-ns//test-operator.v2.0.0 and "
            "@existing/test-ns//test-operator.v1.0.0 originate from package test-operator, "
            "clusterserviceversion test-operator.v1.0.0 exists and is not referenced by a subscription, "
            "subscription test-operator exists, subscription test-operator requires "
            "@existing/test-ns//test-operator.v2.0.0"
        ),
        healthy_subscription
    ]
    sub_api.apply.return_value = Mock()

    install_plan_api = Mock()
    install_plan_api.get.return_value = MockResourceList([
        MockResource(
            name="install-plan-1",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            csv_names=["test-operator.v1.0.0"],
            phase="Complete"
        )
    ])

    def get_resource_api(**kwargs):
        api_version = kwargs["api_version"]
        kind = kwargs["kind"]
        return {
            ("operators.coreos.com/v1alpha1", "Subscription"): sub_api,
            ("operators.coreos.com/v1alpha1", "InstallPlan"): install_plan_api,
        }[(api_version, kind)]

    mock_dyn_client.resources.get.side_effect = get_resource_api

    with patch('mas.devops.olm.Environment', return_value=mock_env):
        result = olm.applySubscription(
            mock_dyn_client,
            "test-namespace",
            "test-operator",
            packageChannel="stable"
        )

    assert result == healthy_subscription
    mock_delete_subscription.assert_called_once_with(mock_dyn_client, "test-namespace", "test-operator")
    mock_delete_installplans.assert_called_once_with(
        install_plan_api,
        "test-namespace",
        "operators.coreos.com/test-operator.test-namespace"
    )
    mock_delete_jobs.assert_called_once_with(mock_dyn_client, "openshift-marketplace")
    assert sub_api.apply.call_count == 2


@patch('mas.devops.olm.deleteSubscription')
@patch('mas.devops.olm.createNamespace')
@patch('mas.devops.olm.ensureOperatorGroupExists')
@patch('mas.devops.olm.getPackageManifest')
@patch('mas.devops.olm.sleep')
def test_catalog_behind_raises_and_cleans_subscription(
    mock_sleep, mock_get_manifest, mock_ensure_og, mock_create_ns, mock_delete_subscription,
    mock_dyn_client, mock_env
):
    mock_get_manifest.return_value = Mock(
        status=Mock(defaultChannel="stable", catalogSource="test-catalog")
    )

    sub_api = Mock()
    sub_api.get.side_effect = [
        MockResourceList([]),
        _constraint_subscription(
            "constraints not satisfiable: @existing/test-ns//test-operator.v1.0.0 and "
            "@existing/test-ns//test-operator.v2.0.0 originate from package test-operator, "
            "clusterserviceversion test-operator.v2.0.0 exists and is not referenced by a subscription, "
            "subscription test-operator exists, subscription test-operator requires "
            "@existing/test-ns//test-operator.v1.0.0"
        )
    ]
    sub_api.apply.return_value = Mock()

    install_plan_api = Mock()
    install_plan_api.get.return_value = MockResourceList([
        MockResource(
            name="install-plan-1",
            labels={"operators.coreos.com/test-operator.test-namespace": ""},
            csv_names=["test-operator.v1.0.0"],
            phase="Complete"
        )
    ])

    def get_resource_api(**kwargs):
        api_version = kwargs["api_version"]
        kind = kwargs["kind"]
        return {
            ("operators.coreos.com/v1alpha1", "Subscription"): sub_api,
            ("operators.coreos.com/v1alpha1", "InstallPlan"): install_plan_api,
        }[(api_version, kind)]

    mock_dyn_client.resources.get.side_effect = get_resource_api

    with patch('mas.devops.olm.Environment', return_value=mock_env):
        with pytest.raises(olm.OLMException, match="Catalog is behind"):
            olm.applySubscription(
                mock_dyn_client,
                "test-namespace",
                "test-operator",
                packageChannel="stable"
            )

    mock_delete_subscription.assert_called_once_with(mock_dyn_client, "test-namespace", "test-operator")

# Made with Bob
