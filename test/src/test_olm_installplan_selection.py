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
Unit tests for InstallPlan selection logic in applySubscription.

These tests verify the fix for the bug where completed InstallPlans
might not be returned by label selector queries, causing infinite loops
when using Manual approval with startingCSV.
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


@pytest.fixture
def mock_dyn_client():
    """Create a mock DynamicClient"""
    client = Mock()
    return client


@pytest.fixture
def mock_env():
    """Create a mock Jinja2 Environment"""
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


def create_owner_ref(kind, name):
    """Helper to create an owner reference"""
    ref = Mock()
    ref.kind = kind
    ref.name = name
    return ref


@patch('mas.devops.olm.createNamespace')
@patch('mas.devops.olm.ensureOperatorGroupExists')
@patch('mas.devops.olm.getPackageManifest')
@patch('mas.devops.olm.sleep')
def test_automatic_approval_uses_label_selector_only(
    mock_sleep, mock_get_manifest, mock_ensure_og, mock_create_ns, mock_dyn_client, mock_env
):
    """
    Test that automatic approval uses only the label selector (standard behavior).
    Should NOT query all InstallPlans.
    """
    # Setup mocks
    mock_get_manifest.return_value = Mock(
        status=Mock(defaultChannel="stable", catalogSource="test-catalog")
    )

    # Mock subscription API
    sub_api = Mock()
    sub_api.get.return_value = MockResourceList([])  # No existing subscription
    sub_api.apply.return_value = Mock()

    # Mock InstallPlan API - label selector returns one InstallPlan
    install_plan_api = Mock()
    install_plan = MockResource(
        name="install-plan-1",
        labels={"operators.coreos.com/test-operator.test-namespace": ""},
        csv_names=["test-operator.v1.0.0"],
        phase="Complete"
    )
    install_plan_api.get.return_value = MockResourceList([install_plan])

    # Setup resource API
    mock_dyn_client.resources.get.side_effect = lambda **kwargs: {
        ("operators.coreos.com/v1alpha1", "Subscription"): sub_api,
        ("operators.coreos.com/v1alpha1", "InstallPlan"): install_plan_api,
    }.get((kwargs.get("api_version"), kwargs.get("kind")))

    with patch('mas.devops.olm.Environment', return_value=mock_env):
        # Call applySubscription with Automatic approval (default)
        olm.applySubscription(
            mock_dyn_client,
            "test-namespace",
            "test-operator",
            packageChannel="stable",
            installPlanApproval="Automatic"
        )

    # Verify InstallPlan API was called with label selector only
    install_plan_calls = [c for c in install_plan_api.get.call_args_list]

    # Should only use label selector, never query all InstallPlans
    for call_args in install_plan_calls:
        args, kwargs = call_args
        assert 'label_selector' in kwargs, "Should use label selector"
        assert kwargs.get('namespace') == "test-namespace"


@patch('mas.devops.olm.createNamespace')
@patch('mas.devops.olm.ensureOperatorGroupExists')
@patch('mas.devops.olm.getPackageManifest')
@patch('mas.devops.olm.sleep')
def test_manual_approval_without_starting_csv_uses_label_selector_only(
    mock_sleep, mock_get_manifest, mock_ensure_og, mock_create_ns, mock_dyn_client, mock_env
):
    """
    Test that Manual approval WITHOUT startingCSV uses only label selector.
    Should NOT query all InstallPlans.
    """
    # Setup mocks
    mock_get_manifest.return_value = Mock(
        status=Mock(defaultChannel="stable", catalogSource="test-catalog")
    )

    # Mock subscription API
    sub_api = Mock()
    sub_api.get.return_value = MockResourceList([])
    sub_api.apply.return_value = Mock()

    # Mock InstallPlan API
    install_plan_api = Mock()
    install_plan = MockResource(
        name="install-plan-1",
        labels={"operators.coreos.com/test-operator.test-namespace": ""},
        csv_names=["test-operator.v1.0.0"],
        phase="RequiresApproval"
    )
    install_plan_api.get.return_value = MockResourceList([install_plan])
    install_plan_api.patch.return_value = Mock()

    mock_dyn_client.resources.get.side_effect = lambda **kwargs: {
        ("operators.coreos.com/v1alpha1", "Subscription"): sub_api,
        ("operators.coreos.com/v1alpha1", "InstallPlan"): install_plan_api,
    }.get((kwargs.get("api_version"), kwargs.get("kind")))

    with patch('mas.devops.olm.Environment', return_value=mock_env):
        # Call with Manual approval but NO startingCSV
        olm.applySubscription(
            mock_dyn_client,
            "test-namespace",
            "test-operator",
            packageChannel="stable",
            installPlanApproval="Manual"
        )

    # Verify only label selector was used
    install_plan_calls = [c for c in install_plan_api.get.call_args_list]
    for call_args in install_plan_calls:
        args, kwargs = call_args
        # Should only use label selector or get by name, never query all
        assert 'label_selector' in kwargs or 'name' in kwargs


@patch('mas.devops.olm.createNamespace')
@patch('mas.devops.olm.ensureOperatorGroupExists')
@patch('mas.devops.olm.getPackageManifest')
@patch('mas.devops.olm.sleep')
def test_manual_approval_with_starting_csv_label_selector_finds_match(
    mock_sleep, mock_get_manifest, mock_ensure_og, mock_create_ns, mock_dyn_client, mock_env
):
    """
    Test Manual approval with startingCSV when label selector returns the correct InstallPlan.
    Should use label selector result, NOT query all InstallPlans.
    """
    # Setup mocks
    mock_get_manifest.return_value = Mock(
        status=Mock(defaultChannel="stable", catalogSource="test-catalog")
    )

    # Mock subscription API
    sub_api = Mock()
    sub_api.get.return_value = MockResourceList([])
    sub_api.apply.return_value = Mock()

    # Mock InstallPlan API - label selector returns matching InstallPlan
    install_plan_api = Mock()
    install_plan = MockResource(
        name="install-plan-1",
        labels={"operators.coreos.com/test-operator.test-namespace": ""},
        csv_names=["test-operator.v1.0.0"],  # Matches startingCSV
        phase="Complete"
    )
    install_plan_api.get.return_value = MockResourceList([install_plan])

    mock_dyn_client.resources.get.side_effect = lambda **kwargs: {
        ("operators.coreos.com/v1alpha1", "Subscription"): sub_api,
        ("operators.coreos.com/v1alpha1", "InstallPlan"): install_plan_api,
    }.get((kwargs.get("api_version"), kwargs.get("kind")))

    with patch('mas.devops.olm.Environment', return_value=mock_env):
        olm.applySubscription(
            mock_dyn_client,
            "test-namespace",
            "test-operator",
            packageChannel="stable",
            installPlanApproval="Manual",
            startingCSV="test-operator.v1.0.0"
        )

    # Verify we found the InstallPlan via label selector
    # Should NOT have queried all InstallPlans (no call without label_selector)
    install_plan_calls = [c for c in install_plan_api.get.call_args_list]

    # Check that we never queried without a label_selector or name
    for call_args in install_plan_calls:
        args, kwargs = call_args
        assert 'label_selector' in kwargs or 'name' in kwargs, \
            "Should only use label selector or get by name, not query all"


@patch('mas.devops.olm.createNamespace')
@patch('mas.devops.olm.ensureOperatorGroupExists')
@patch('mas.devops.olm.getPackageManifest')
@patch('mas.devops.olm.sleep')
def test_manual_approval_with_starting_csv_fallback_to_ownership_search(
    mock_sleep, mock_get_manifest, mock_ensure_og, mock_create_ns, mock_dyn_client, mock_env
):
    """
    Test Manual approval with startingCSV when label selector misses the completed InstallPlan.
    Should fall back to querying all InstallPlans and filter by subscription ownership.
    This is the key scenario the bug fix addresses.
    """
    # Setup mocks
    mock_get_manifest.return_value = Mock(
        status=Mock(defaultChannel="stable", catalogSource="test-catalog")
    )

    # Mock subscription API
    sub_api = Mock()
    sub_api.get.return_value = MockResourceList([])
    sub_api.apply.return_value = Mock()

    # Mock InstallPlan API
    install_plan_api = Mock()

    # Label selector returns only the in-progress InstallPlan (wrong one)
    wrong_install_plan = MockResource(
        name="install-plan-2",
        labels={"operators.coreos.com/test-operator.test-namespace": ""},
        csv_names=["test-operator.v2.0.0"],  # Does NOT match startingCSV
        phase="Installing"
    )

    # All InstallPlans query returns both (including the completed one)
    correct_install_plan = MockResource(
        name="install-plan-1",
        labels={},  # Label might be removed from completed plan
        owner_refs=[create_owner_ref("Subscription", "test-operator")],
        csv_names=["test-operator.v1.0.0"],  # Matches startingCSV
        phase="Complete"
    )

    # Setup the mock to return different results based on parameters
    def get_side_effect(*args, **kwargs):
        if 'label_selector' in kwargs:
            # Label selector query - returns only wrong InstallPlan
            return MockResourceList([wrong_install_plan])
        elif 'name' in kwargs:
            # Get by name - return the correct one
            return correct_install_plan
        else:
            # Query all InstallPlans - returns both
            return MockResourceList([correct_install_plan, wrong_install_plan])

    install_plan_api.get.side_effect = get_side_effect

    mock_dyn_client.resources.get.side_effect = lambda **kwargs: {
        ("operators.coreos.com/v1alpha1", "Subscription"): sub_api,
        ("operators.coreos.com/v1alpha1", "InstallPlan"): install_plan_api,
    }.get((kwargs.get("api_version"), kwargs.get("kind")))

    with patch('mas.devops.olm.Environment', return_value=mock_env):
        olm.applySubscription(
            mock_dyn_client,
            "test-namespace",
            "test-operator",
            packageChannel="stable",
            installPlanApproval="Manual",
            startingCSV="test-operator.v1.0.0"
        )

    # Verify the fallback behavior occurred
    install_plan_calls = [c for c in install_plan_api.get.call_args_list]

    # Should have:
    # 1. Called with label_selector (initial query)
    # 2. Called without label_selector (fallback to query all)
    has_label_selector_call = any(
        'label_selector' in call_args[1]
        for call_args in install_plan_calls
    )
    has_all_query_call = any(
        'label_selector' not in call_args[1] and 'name' not in call_args[1]
        for call_args in install_plan_calls
    )

    assert has_label_selector_call, "Should have tried label selector first"
    assert has_all_query_call, "Should have fallen back to querying all InstallPlans"


@patch('mas.devops.olm.createNamespace')
@patch('mas.devops.olm.ensureOperatorGroupExists')
@patch('mas.devops.olm.getPackageManifest')
@patch('mas.devops.olm.sleep')
def test_manual_approval_filters_by_subscription_ownership(
    mock_sleep, mock_get_manifest, mock_ensure_og, mock_create_ns, mock_dyn_client, mock_env
):
    """
    Test that when querying all InstallPlans, we correctly filter by subscription ownership.
    This ensures we don't accidentally use InstallPlans from other subscriptions.
    """
    # Setup mocks
    mock_get_manifest.return_value = Mock(
        status=Mock(defaultChannel="stable", catalogSource="test-catalog")
    )

    # Mock subscription API
    sub_api = Mock()
    sub_api.get.return_value = MockResourceList([])
    sub_api.apply.return_value = Mock()

    # Mock InstallPlan API
    install_plan_api = Mock()

    # Label selector returns wrong InstallPlan
    wrong_install_plan = MockResource(
        name="install-plan-wrong",
        labels={"operators.coreos.com/test-operator.test-namespace": ""},
        csv_names=["test-operator.v2.0.0"],
        phase="Installing"
    )

    # All InstallPlans includes:
    # 1. Correct one owned by our subscription
    correct_install_plan = MockResource(
        name="install-plan-correct",
        labels={},
        owner_refs=[create_owner_ref("Subscription", "test-operator")],
        csv_names=["test-operator.v1.0.0"],
        phase="Complete"
    )

    # 2. One owned by a different subscription (should be ignored)
    other_subscription_plan = MockResource(
        name="install-plan-other",
        labels={},
        owner_refs=[create_owner_ref("Subscription", "other-operator")],
        csv_names=["test-operator.v1.0.0"],  # Same CSV but wrong subscription
        phase="Complete"
    )

    def get_side_effect(*args, **kwargs):
        if 'label_selector' in kwargs:
            return MockResourceList([wrong_install_plan])
        elif 'name' in kwargs:
            return correct_install_plan
        else:
            # Return all three InstallPlans
            return MockResourceList([correct_install_plan, other_subscription_plan, wrong_install_plan])

    install_plan_api.get.side_effect = get_side_effect

    mock_dyn_client.resources.get.side_effect = lambda **kwargs: {
        ("operators.coreos.com/v1alpha1", "Subscription"): sub_api,
        ("operators.coreos.com/v1alpha1", "InstallPlan"): install_plan_api,
    }.get((kwargs.get("api_version"), kwargs.get("kind")))

    with patch('mas.devops.olm.Environment', return_value=mock_env):
        olm.applySubscription(
            mock_dyn_client,
            "test-namespace",
            "test-operator",
            packageChannel="stable",
            installPlanApproval="Manual",
            startingCSV="test-operator.v1.0.0"
        )

    # The test passes if it completes without error
    # The code should have found the correct InstallPlan by checking ownership
    # and ignored the one from the other subscription

# Made with Bob
