# *****************************************************************************
# Copyright (c) 2025 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

import pytest
from unittest import mock
from unittest.mock import MagicMock
from openshift.dynamic.exceptions import NotFoundError
from kubernetes.client.rest import ApiException

from mas.devops import mas


CATALOG_ID = 'v9-250101-amd64'
CATALOG_DISPLAY_NAME_VALID = f'IBM Maximo Operators {CATALOG_ID}'
CATALOG_DISPLAY_NAME_INVALID = 'invalidCatalogName'
IMAGE = 'testImage'


##############################################################################
# WARNING: All tests must be written with strictly no external dependencies.
# Mocks must be used in place of any calls to OpenShift API etc.
##############################################################################


@pytest.fixture(autouse=True)
@mock.patch('openshift.dynamic.DynamicClient')
def dynamic_client(client):
    return client


def test_get_current_catalog_success(dynamic_client):
    client = dynamic_client()
    resources = MagicMock()
    catalog_api = MagicMock()
    resources.get.side_effect = lambda **kwargs: catalog_api if kwargs['api_version'] == 'operators.coreos.com/v1alpha1' \
        and kwargs['kind'] == 'CatalogSource' else None
    client.resources = resources
    catalog = MagicMock()
    catalog_api.get.side_effect = lambda **kwargs: catalog if kwargs['name'] == 'ibm-operator-catalog' \
        and kwargs['namespace'] == 'openshift-marketplace' else None
    spec = MagicMock()
    catalog.spec = spec
    spec.displayName = CATALOG_DISPLAY_NAME_VALID
    spec.image = IMAGE
    current_catalog = mas.getCurrentCatalog(client)
    assert current_catalog['displayName'] == CATALOG_DISPLAY_NAME_VALID
    assert current_catalog['catalogId'] == CATALOG_ID
    assert current_catalog['image'] == IMAGE


def test_get_current_catalog_not_found(dynamic_client):
    client = dynamic_client()
    resources = MagicMock()
    catalog_api = MagicMock()
    resources.get.side_effect = lambda **kwargs: catalog_api if kwargs['api_version'] == 'operators.coreos.com/v1alpha1' \
        and kwargs['kind'] == 'CatalogSource' else None
    client.resources = resources
    catalog_api.get.side_effect = NotFoundError(ApiException(status='404'))
    assert mas.getCurrentCatalog(client) is None


def test_get_current_catalog_invalid_id(dynamic_client):
    client = dynamic_client()
    resources = MagicMock()
    catalog_api = MagicMock()
    resources.get.side_effect = lambda **kwargs: catalog_api if kwargs['api_version'] == 'operators.coreos.com/v1alpha1' \
        and kwargs['kind'] == 'CatalogSource' else None
    client.resources = resources
    catalog = MagicMock()
    catalog_api.get.side_effect = lambda **kwargs: catalog if kwargs['name'] == 'ibm-operator-catalog' \
        and kwargs['namespace'] == 'openshift-marketplace' else None
    spec = MagicMock()
    catalog.spec = spec
    spec.displayName = CATALOG_DISPLAY_NAME_INVALID
    spec.image = IMAGE
    current_catalog = mas.getCurrentCatalog(client)
    assert current_catalog['displayName'] == CATALOG_DISPLAY_NAME_INVALID
    assert current_catalog['image'] == IMAGE
    assert current_catalog['catalogId'] is None
