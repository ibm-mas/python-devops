# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from openshift import dynamic
from kubernetes import config
from kubernetes.client import api_client

from mas.devops import olm, ocp

dynClient = dynamic.DynamicClient(
    api_client.ApiClient(configuration=config.load_kube_config())
)


def test_get_manifest():
    manifest = olm.getPackageManifest(dynClient, "ibm-sls")
    assert manifest is not None
    assert manifest.metadata.name == "ibm-sls"
    assert manifest.status.catalogSource == "ibm-operator-catalog"
    assert manifest.status.catalogSourceNamespace == "openshift-marketplace"
    assert manifest.status.catalogSourcePublisher == "IBM"
    assert manifest.status.defaultChannel == "3.x-stable"
    assert manifest.status.packageName == "ibm-sls"


def test_get_manifest_none():
    manifest = olm.getPackageManifest(dynClient, "ibm-sls2")
    assert manifest is None


def test_crud():
    namespace = "cli-fvt-1"
    subscription = olm.applySubscription(dynClient, namespace, "ibm-sls", packageChannel="3.x")
    assert subscription.metadata.name == "ibm-sls"
    assert subscription.metadata.namespace == namespace

    # When we install the ibm-sls subscription OLM will automatically create the ibm-truststore-mgr
    # subscription, but when we delete the subscription, OLM will not automatically remove the latter
    olm.deleteSubscription(dynClient, namespace, "ibm-sls")
    olm.deleteSubscription(dynClient, namespace, "ibm-truststore-mgr")
    ocp.deleteNamespace(dynClient, namespace)


def test_crud_with_config():
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
