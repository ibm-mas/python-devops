# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

import pytest
from openshift import dynamic
from kubernetes import config
from kubernetes.client import api_client

from mas.devops import olm, ocp

pytestmark = pytest.mark.openshift


@pytest.fixture(scope="module")
def dynClient():
    """Create DynamicClient for OpenShift cluster access."""
    return dynamic.DynamicClient(
        api_client.ApiClient(configuration=config.load_kube_config())
    )


def test_get_manifest(dynClient):
    manifest = olm.getPackageManifest(dynClient, "ibm-sls")
    assert manifest is not None
    assert manifest.metadata.name == "ibm-sls"
    assert manifest.status.catalogSource == "ibm-operator-catalog"
    assert manifest.status.catalogSourceNamespace == "openshift-marketplace"
    assert manifest.status.catalogSourcePublisher == "IBM"
    assert manifest.status.defaultChannel == "3.x-stable"
    assert manifest.status.packageName == "ibm-sls"


def test_get_manifest_none(dynClient):
    manifest = olm.getPackageManifest(dynClient, "ibm-sls2")
    assert manifest is None


def test_crud(dynClient):
    namespace = "cli-fvt-1"
    subscription = olm.applySubscription(dynClient, namespace, "ibm-sls", packageChannel="3.x")
    assert subscription.metadata.name == "ibm-sls"
    assert subscription.metadata.namespace == namespace

    subscriptionLookup1 = olm.getSubscription(dynClient, namespace, "ibm-sls")
    subscriptionLookup2 = olm.getSubscription(dynClient, namespace, "ibm-truststore-mgr")

    assert subscriptionLookup1.metadata.name == "ibm-sls"
    assert subscriptionLookup1.metadata.namespace == namespace
    assert subscriptionLookup1.spec.channel == "3.x"
    assert subscriptionLookup2.metadata.namespace == namespace
    assert subscriptionLookup2.spec.channel == "1.x-stable"

    # When we install the ibm-sls subscription OLM will automatically create the ibm-truststore-mgr
    # subscription, but when we delete the subscription, OLM will not automatically remove the latter
    olm.deleteSubscription(dynClient, namespace, "ibm-sls")
    olm.deleteSubscription(dynClient, namespace, "ibm-truststore-mgr")
    ocp.deleteNamespace(dynClient, namespace)

    failedSubscriptionLookup1 = olm.getSubscription(dynClient, namespace, "ibm-sls")
    failedSubscriptionLookup2 = olm.getSubscription(dynClient, namespace, "ibm-truststore-mgr")
    assert failedSubscriptionLookup1 is None
    assert failedSubscriptionLookup2 is None


def test_crud_with_config(dynClient):
    namespace = "cli-fvt-2"
    # We don't need this, just want to test that it works
    testConfig = {
        "env": [
            {"name": "DUMMY_ENV_VAR", "value": "testing"}
        ]
    }
    subscription = olm.applySubscription(dynClient, namespace, "ibm-sls", packageChannel="3.x", config=testConfig)
    assert subscription.metadata.name == "ibm-sls"
    assert subscription.metadata.namespace == namespace

    # When we install the ibm-sls subscription OLM will automatically create the ibm-truststore-mgr
    # subscription, but when we delete the subscription, OLM will not automatically remove the latter
    olm.deleteSubscription(dynClient, namespace, "ibm-sls")
    olm.deleteSubscription(dynClient, namespace, "ibm-truststore-mgr")
    ocp.deleteNamespace(dynClient, namespace)


def test_crud_with_manual_approval(dynClient):
    """
    Test that when installPlanApproval is Manual without a startingCSV,
    an OLMException is raised.
    """
    namespace = "cli-fvt-3"

    # This should raise an OLMException because Manual approval requires a startingCSV
    try:
        olm.applySubscription(
            dynClient,
            namespace,
            "ibm-sls",
            packageChannel="3.x",
            installPlanApproval="Manual"
        )
        # If we get here, the test should fail
        assert False, "Expected OLMException to be raised when installPlanApproval is Manual without startingCSV"
    except olm.OLMException as e:
        # Verify the error message is correct
        assert "When installPlanApproval is 'Manual', a startingCSV must be provided" in str(e)
        # Test passed - exception was raised as expected


def test_crud_with_starting_csv(dynClient):
    namespace = "cli-fvt-4"
    # Note: This test assumes a specific CSV version exists in the catalog
    # You may need to adjust the version based on what's available
    subscription = olm.applySubscription(
        dynClient,
        namespace,
        "ibm-sls",
        packageChannel="3.x",
        startingCSV="ibm-sls.v3.8.0"
    )
    assert subscription.metadata.name == "ibm-sls"
    assert subscription.metadata.namespace == namespace
    assert subscription.spec.startingCSV == "ibm-sls.v3.8.0"

    # When we install the ibm-sls subscription OLM will automatically create the ibm-truststore-mgr
    # subscription, but when we delete the subscription, OLM will not automatically remove the latter
    olm.deleteSubscription(dynClient, namespace, "ibm-sls")
    olm.deleteSubscription(dynClient, namespace, "ibm-truststore-mgr")
    ocp.deleteNamespace(dynClient, namespace)


def test_crud_with_manual_approval_and_starting_csv(dynClient):
    """
    Test that when installPlanApproval is Manual and startingCSV is specified,
    the first InstallPlan is automatically approved to reach the startingCSV.
    This allows the initial installation to proceed without manual intervention.

    Note: With Manual approval and startingCSV, the subscription state will be
    "UpgradePending" after installation (indicating newer versions are available
    but require manual approval), not "AtLatestKnown".
    """
    namespace = "cli-fvt-5"
    subscription = olm.applySubscription(
        dynClient,
        namespace,
        "ibm-sls",
        packageChannel="3.x",
        installPlanApproval="Manual",
        startingCSV="ibm-sls.v3.8.0"
    )
    assert subscription.metadata.name == "ibm-sls"
    assert subscription.metadata.namespace == namespace
    assert subscription.spec.installPlanApproval == "Manual"
    assert subscription.spec.startingCSV == "ibm-sls.v3.8.0"

    # Verify that the subscription reached UpgradePending state
    # This confirms the InstallPlan was automatically approved and installed
    # UpgradePending indicates newer versions are available but require manual approval
    assert subscription.status.state == "UpgradePending"

    # Verify the installed CSV matches the startingCSV
    installedCSV = subscription.status.installedCSV
    assert installedCSV == "ibm-sls.v3.8.0"

    # When we install the ibm-sls subscription OLM will automatically create the ibm-truststore-mgr
    # subscription, but when we delete the subscription, OLM will not automatically remove the latter
    olm.deleteSubscription(dynClient, namespace, "ibm-sls")
    olm.deleteSubscription(dynClient, namespace, "ibm-truststore-mgr")
    ocp.deleteNamespace(dynClient, namespace)
