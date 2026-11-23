# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

import pytest
import requests
from unittest.mock import patch, MagicMock

from mas.devops.utils import validateIBMEntitlementKey, EntitlementKeySSLError


@patch("mas.devops.utils.requests.get")
def test_ssl_error_raises_entitlement_key_ssl_error(mock_get):
    mock_get.side_effect = requests.exceptions.SSLError("self-signed certificate in certificate chain")
    with pytest.raises(EntitlementKeySSLError):
        validateIBMEntitlementKey("key-123")


@patch("mas.devops.utils.requests.get")
def test_ssl_error_is_a_request_exception(mock_get):
    mock_get.side_effect = requests.exceptions.SSLError("ssl failure")
    with pytest.raises(requests.exceptions.RequestException):
        validateIBMEntitlementKey("key-123")


@patch("mas.devops.utils.requests.get")
def test_other_request_exception_is_reraised_unchanged(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("unreachable")
    with pytest.raises(requests.exceptions.ConnectionError) as excInfo:
        validateIBMEntitlementKey("key-123")
    assert not isinstance(excInfo.value, EntitlementKeySSLError)


@patch("mas.devops.utils.requests.get")
def test_unexpected_status_returns_false(mock_get):
    mock_get.return_value = MagicMock(status_code=500)
    assert validateIBMEntitlementKey("key-123") is False
