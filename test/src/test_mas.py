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
from kubernetes.dynamic.resource import ResourceInstance

from mas.devops import mas

pytestmark = pytest.mark.openshift


@pytest.fixture(scope="module")
def dynClient():
    """Create DynamicClient for OpenShift cluster access."""
    return dynamic.DynamicClient(
        api_client.ApiClient(configuration=config.load_kube_config())
    )


def test_entitlement(dynClient):
    icrUsername = "testing-i"
    icrPassword = "not-a-real-password-i"

    secret = mas.updateIBMEntitlementKey(dynClient, "default", icrUsername, icrPassword)
    assert secret is not None
    assert isinstance(secret, ResourceInstance)
    assert secret.metadata.name == "ibm-entitlement"


def test_entitlement_with_artifactory(dynClient):
    artifactoryUsername = "testing-a"
    artifactoryPassword = "not-a-real-password-a"

    icrUsername = "testing-i"
    icrPassword = "not-a-real-password-i"

    secret = mas.updateIBMEntitlementKey(
        dynClient,
        "default",
        icrUsername,
        icrPassword,
        artifactoryUsername,
        artifactoryPassword,
    )
    assert secret is not None
    assert isinstance(secret, ResourceInstance)
    assert secret.metadata.name == "ibm-entitlement"


def test_entitlement_alt_name(dynClient):
    icrUsername = "testing-i"
    icrPassword = "not-a-real-password-i"

    secret = mas.updateIBMEntitlementKey(
        dynClient, "default", icrUsername, icrPassword, secretName="ibm-entitlement-key"
    )
    assert secret is not None
    assert isinstance(secret, ResourceInstance)
    assert secret.metadata.name == "ibm-entitlement-key"


def test_get_channel(dynClient):
    channel = mas.getMasChannel(dynClient, "doesnotexist")
    assert channel is None


def test_is_airgap_install(dynClient):
    # The cluster we are using to test with does not have the MAS ICSP or IDMS installed
    assert mas.isAirgapInstall(dynClient) is False
    assert mas.isAirgapInstall(dynClient, checkICSP=False) is False


def test_get_mas_public_cluster_issuer(dynClient):
    # Test with non-existent instance - should return None
    issuer = mas.getMasPublicClusterIssuer(dynClient, "doesnotexist")
    assert issuer is None


# def test_is_app_ready(dynClient):
#     mas.waitForAppReady(dynClient, "fvtcpd", "iot")
#     mas.waitForAppReady(dynClient, "fvtcpd", "iot", "masdev")
