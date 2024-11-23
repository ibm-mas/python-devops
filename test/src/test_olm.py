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

# from openshift import dynamic
# from kubernetes import config
# from kubernetes.client import api_client

from mas.devops import olm

# dynClient = dynamic.DynamicClient(
#     api_client.ApiClient(configuration=config.load_kube_config())
# )
dynClient = None


@pytest.mark.skip(reason="Need to configure access to OCP")
def test_get_manifest():
    manifest = olm.getPackageManifest(dynClient, "ibm-sls")
    assert manifest is not None
    assert manifest.metadata.name == "ibm-sls"
    assert manifest.metadata.status.catalogSource == "ibm-operator-catalog"
    assert manifest.metadata.status.catalogSourceNamespace == "openshift-marketplace"
    assert manifest.metadata.status.catalogSourcePublisher == "IBM"
    assert manifest.metadata.status.defaultChannel == "3.x"
    assert manifest.metadata.status.packageName == "ibm-sls"


@pytest.mark.skip(reason="Need to configure access to OCP")
def test_get_manifest_none():
    manifest = olm.getPackageManifest(dynClient, "ibm-sls2")
    assert manifest is None


@pytest.mark.skip(reason="Need to configure access to OCP")
def test_crud():
    subscription = olm.applySubscription(dynClient, "namespace1", "sub1", "ibm-sls")
    assert subscription.metadata.name == "sub1"
    assert subscription.metadata.namespace == "namespace1"

    # When we install the ibm-sls subscription OLM will automatically create the ibm-truststore-mgr
    # subscription, but when we delete the subscription, OLM will not automatically remove the latter
    olm.deleteSubscription(dynClient, "namespace1", "ibm-sls")
    olm.deleteSubscription(dynClient, "namespace1", "ibm-truststore-mgr")


@pytest.mark.skip(reason="Need to configure access to OCP")
def test_crud_with_config():
    # We don't need this, just want to test that it works
    testConfig = {
        "env": [
            {"name": "DUMMY_ENV_VAR", "value": "testing"}
        ]
    }
    subscription = olm.applySubscription(dynClient, "namespace1", "sub1", "ibm-sls", config=testConfig)
    assert subscription.metadata.name == "sub1"
    assert subscription.metadata.namespace == "namespace1"

    # When we install the ibm-sls subscription OLM will automatically create the ibm-truststore-mgr
    # subscription, but when we delete the subscription, OLM will not automatically remove the latter
    olm.deleteSubscription(dynClient, "namespace1", "ibm-sls")
    olm.deleteSubscription(dynClient, "namespace1", "ibm-truststore-mgr")
