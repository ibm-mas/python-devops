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
from kubernetes.dynamic.resource import ResourceInstance

from mas.devops import mas

dynClient = dynamic.DynamicClient(
    api_client.ApiClient(configuration=config.load_kube_config())
)


def test_entitlement():
    icrUsername = "testing-i"
    icrPassword = "not-a-real-password-i"

    secret = mas.updateIBMEntitlementKey(dynClient, "default", icrUsername, icrPassword)
    assert secret is not None
    assert isinstance(secret, ResourceInstance)
    assert secret.metadata.name == "ibm-entitlement"


def test_entitlement_with_artifactory():
    artifactoryUsername = "testing-a"
    artifactoryPassword = "not-a-real-password-a"

    icrUsername = "testing-i"
    icrPassword = "not-a-real-password-i"

    secret = mas.updateIBMEntitlementKey(dynClient, "default", icrUsername, icrPassword, artifactoryUsername, artifactoryPassword)
    assert secret is not None
    assert isinstance(secret, ResourceInstance)
    assert secret.metadata.name == "ibm-entitlement"


def test_entitlement_alt_name():
    icrUsername = "testing-i"
    icrPassword = "not-a-real-password-i"

    secret = mas.updateIBMEntitlementKey(dynClient, "default", icrUsername, icrPassword, secretName="ibm-entitlement-key")
    assert secret is not None
    assert isinstance(secret, ResourceInstance)
    assert secret.metadata.name == "ibm-entitlement-key"


def test_get_channel():
    channel = mas.getMasChannel(dynClient, "doesnotexist")
    assert channel is None


def test_is_airgap_install():
    # The cluster we are using to test with does not have the MAS ICSP or IDMS installed
    assert mas.isAirgapInstall(dynClient) is False
    assert mas.isAirgapInstall(dynClient, checkICSP=False) is False
    
def test_version_before():
    assert mas.isVersionBefore('9.1.0','9.1.x-feature') is False
    assert mas.isVersionBefore('9.1.0','9.0.0') is True
    assert mas.isVersionBefore('8.11.1','9.1.0') is False
    assert mas.isVersionBefore('9.1.0','9.1.x-stable') is False

def test_version_equal_of_after():
    assert mas.isVersionEqualOrAfter('9.1.0','9.2.x-feature') is True
    assert mas.isVersionEqualOrAfter('9.1.0','9.0.0') is False
    assert mas.isVersionEqualOrAfter('8.11.1','9.1.0') is True
    assert mas.isVersionEqualOrAfter('9.2.0','9.1.x-stable') is False

if __name__ == '__main__':
    test_version_before()