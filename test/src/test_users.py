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
import base64
from unittest.mock import MagicMock, patch, call
from pytest import fixture
from packaging.version import Version
import os

from mas.devops.users import MASUserUtils

SUPERUSER_USERNAME = "superuser_username"
SUPERUSER_PASSWORD = "superuser_password"  # pragma: allowlist secret


ADMINDASHBOARD_CA_CRT = "admindashboard-ca"
COREAPI_CA_CRT = "coreapi-ca"
MANAGE_CA_CRT = "manage-ca"
MANAGE_TLS_CRT = "manage-tls-crt"
MANAGE_TLS_KEY = "manage-tls-key"

TOKEN = "TOKEN"
MAS_INSTANCE_ID = "inst1"
MAS_WORKSPACE_ID = "masdev"

MAS_CORE_NAMESPACE = f"mas-{MAS_INSTANCE_ID}-core"
MANAGE_NAMESPACE = f"mas-{MAS_INSTANCE_ID}-manage"

ADMIN_DASHBOARD_PORT = 1
COREAPI_PORT = 2
MANAGE_API_PORT = 3

MAS_ADMIN_URL = f"https://admin-dashboard.{MAS_CORE_NAMESPACE}.svc.cluster.local:{ADMIN_DASHBOARD_PORT}"
MAS_API_URL = f"https://coreapi.{MAS_CORE_NAMESPACE}.svc.cluster.local:{COREAPI_PORT}"
MANAGE_API_URL = f"https://{MAS_INSTANCE_ID}-{MAS_WORKSPACE_ID}.{MANAGE_NAMESPACE}.svc.cluster.local:{MANAGE_API_PORT}"

PEM_PATH = "pempath"


def additional_matcher(req, json=None, verify=PEM_PATH, cert=None):
    if json is not None:
        assert req.json() == json
    assert req.verify == verify
    assert req.cert == cert
    return True


def get_secret(name, namespace):
    if name == f"{MAS_INSTANCE_ID}-credentials-superuser":
        data = {
            "username": base64.b64encode(SUPERUSER_USERNAME.encode("utf-8")),
            "password": base64.b64encode(SUPERUSER_PASSWORD.encode("utf-8")),
        }

    if name == f"{MAS_INSTANCE_ID}-admindashboard-cert-internal":
        data = {"ca.crt": base64.b64encode(ADMINDASHBOARD_CA_CRT.encode("utf-8"))}

    if name == f"{MAS_INSTANCE_ID}-coreapi-cert-internal":
        data = {"ca.crt": base64.b64encode(COREAPI_CA_CRT.encode("utf-8"))}

    if name == f"{MAS_INSTANCE_ID}-internal-manage-tls":
        data = {
            "ca.crt": base64.b64encode(MANAGE_CA_CRT.encode("utf-8")),
            "tls.crt": base64.b64encode(MANAGE_TLS_CRT.encode("utf-8")),
            "tls.key": base64.b64encode(MANAGE_TLS_KEY.encode("utf-8")),
        }

    return MagicMock(data=data)


@fixture
def mock_atexit():
    with patch("atexit.register") as mock_atexit:
        yield mock_atexit


@fixture
def mock_named_temporary_file(mock_atexit):
    with patch("tempfile.NamedTemporaryFile") as mock_named_temporary_file:
        mock_file = MagicMock()
        mock_file.name = PEM_PATH
        mock_named_temporary_file.return_value.__enter__.return_value = mock_file
        yield mock_file


@fixture
def mock_v1_secrets():
    with patch("mas.devops.users.DynamicClient") as mock_DynamicClientCls:
        mock_DynamicClient = mock_DynamicClientCls.return_value
        mock_v1_secrets = mock_DynamicClient.resources.get.return_value
        mock_v1_secrets.get.side_effect = get_secret
        yield mock_v1_secrets


@fixture
def mock_logininitial_endpoint(requests_mock):
    yield requests_mock.post(
        f"{MAS_ADMIN_URL}/logininitial",
        json=dict(token=TOKEN),
        additional_matcher=lambda req: additional_matcher(req, json={"username": SUPERUSER_USERNAME, "password": SUPERUSER_PASSWORD}),
    )


@fixture(params=["9.0", "9.1"])
def user_utils(
    request,
    mock_v1_secrets,
    mock_logininitial_endpoint,
    mock_named_temporary_file,
    mock_atexit,
):
    k8s_client = MagicMock()  # DynamicClient is mocked out, no methods will be called on the k8s_client
    mas_version = request.param
    user_utils = MASUserUtils(
        MAS_INSTANCE_ID,
        MAS_WORKSPACE_ID,
        k8s_client,
        mas_version=mas_version,
        coreapi_port=COREAPI_PORT,
        admin_dashboard_port=ADMIN_DASHBOARD_PORT,
        manage_api_port=MANAGE_API_PORT,
    )

    yield user_utils


@fixture
def mock_manage_api_key(requests_mock):
    """
    Setup mock Manage APIs for setting up an API Key
    """
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "apikey": "test-api-key-12345",
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }  # pragma: allowlist secret

    # Also setup for MXINTADM user
    mxintadm_apikey = {
        "userid": "MXINTADM",
        "apikey": "mxintadm-api-key-67890",
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/mxintadmapikeyid",
    }  # pragma: allowlist secret

    def mxintadm_matcher(req):
        return req.json().get("userid") == "MXINTADM" and req.verify == PEM_PATH and req.cert == PEM_PATH

    def user1_matcher(req):
        return req.json().get("userid") == user_id and req.verify == PEM_PATH and req.cert == PEM_PATH

    # Mock for MXINTADM API key creation (returns 400 - key already exists)
    requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1",
        request_headers={"content-type": "application/json"},
        json={
            "Error": {
                "reasonCode": "BMXAA10051E",
                "message": "Only one API key allowed per user",
            }
        },
        status_code=400,
        additional_matcher=mxintadm_matcher,
    )

    # Mock for user1 API key creation
    requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1",
        request_headers={"content-type": "application/json"},
        json={"id": user_id},
        status_code=201,
        additional_matcher=user1_matcher,
    )

    # Mock for user1 API key retrieval
    requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1&oslc.select=*&oslc.where=userid="{user_id}"',
        request_headers={"accept": "application/json"},
        json={"member": [apikey]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    # Mock for MXINTADM API key retrieval (returns existing key)
    requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1&oslc.select=*&oslc.where=userid="MXINTADM"',
        request_headers={"accept": "application/json"},
        json={"member": [mxintadm_apikey]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    yield mxintadm_apikey


def test_admin_internal_ca_pem_file_path(user_utils, mock_named_temporary_file, mock_atexit):
    assert str(user_utils.admin_internal_ca_pem_file_path) == PEM_PATH
    assert mock_named_temporary_file.mock_calls == [
        call.write(ADMINDASHBOARD_CA_CRT.encode()),
        call.flush(),
        call.close(),
    ]
    assert mock_atexit.mock_calls == [call(os.remove, PEM_PATH)]

    # verify caching
    assert str(user_utils.admin_internal_ca_pem_file_path) == PEM_PATH
    assert mock_named_temporary_file.mock_calls == [
        call.write(ADMINDASHBOARD_CA_CRT.encode()),
        call.flush(),
        call.close(),
    ]
    assert mock_atexit.mock_calls == [call(os.remove, PEM_PATH)]


def mock_get_user(requests_mock, user_id, json, status_code, mock_manage_api_key, json_manage=None):
    # Mock Core API endpoint for version < 9.1
    core_mock = requests_mock.get(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json=json,
        status_code=status_code,
        additional_matcher=lambda req: additional_matcher(req),
    )

    # Use separate JSON for Manage API if provided, otherwise use the same
    manage_json = json_manage if json_manage is not None else json

    # Mock Manage API endpoint for version >= 9.1
    # First request: Uses query parameter oslc.where with user.userid to get resource_id
    manage_query_mock = requests_mock.get(
        f"{MANAGE_API_URL}/maximo/api/os/masperuser?lean=1&oslc.where=user.userid%3D%22{user_id}%22",
        request_headers={"apikey": mock_manage_api_key["apikey"]},
        json=manage_json,
        status_code=status_code,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    # Second request: Mock the query-based request with personid
    # Always mock this for version >= 9.1, regardless of status_code
    manage_personid_mock = requests_mock.get(
        f"{MANAGE_API_URL}/maximo/api/os/masperuser/?lean=1&oslc.where=personid%3D%22{user_id}%22&oslc.select=personid%2Cdisplayname",
        request_headers={"apikey": mock_manage_api_key["apikey"]},
        json=manage_json,
        status_code=status_code,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    return core_mock, manage_query_mock, manage_personid_mock


def mock_get_user_200(requests_mock, user_id, mock_manage_api_key):
    # Core API response for version < 9.1
    core_json = {"id": user_id, "displayName": user_id}

    # Manage API response for version >= 9.1
    # Include member array with href containing resource_id
    resource_id = f"{user_id}_resource_id"
    manage_json = {
        "member": [
            {
                "href": f"api/os/masperuser/{resource_id}",
                "personid": user_id,
                "displayname": user_id,
            }
        ]
    }

    return mock_get_user(
        requests_mock,
        user_id,
        core_json,
        200,
        mock_manage_api_key,
        json_manage=manage_json,
    )


def mock_get_user_404(requests_mock, user_id, mock_manage_api_key):
    return mock_get_user(requests_mock, user_id, {"error": "notfound"}, 404, mock_manage_api_key)


def mock_get_user_500(requests_mock, user_id, mock_manage_api_key):
    return mock_get_user(requests_mock, user_id, {"error": "internal"}, 500, mock_manage_api_key)


def test_mas_superuser_credentials(user_utils, mock_v1_secrets):
    assert mock_v1_secrets.get.call_count == 0
    assert user_utils.mas_superuser_credentials == {
        "username": SUPERUSER_USERNAME,
        "password": SUPERUSER_PASSWORD,
    }
    assert mock_v1_secrets.get.call_count == 1
    # verify caching is working
    assert user_utils.mas_superuser_credentials == {
        "username": SUPERUSER_USERNAME,
        "password": SUPERUSER_PASSWORD,
    }
    assert mock_v1_secrets.get.call_count == 1


def test_admin_internal_tls_secret(user_utils, mock_v1_secrets):
    assert mock_v1_secrets.get.call_count == 0
    assert user_utils.admin_internal_tls_secret.data["ca.crt"] == base64.b64encode(ADMINDASHBOARD_CA_CRT.encode("utf-8"))
    assert mock_v1_secrets.get.call_count == 1
    assert user_utils.admin_internal_tls_secret.data["ca.crt"] == base64.b64encode(ADMINDASHBOARD_CA_CRT.encode("utf-8"))
    assert mock_v1_secrets.get.call_count == 1


def test_core_internal_tls_secret(user_utils, mock_v1_secrets):
    assert mock_v1_secrets.get.call_count == 0
    assert user_utils.core_internal_tls_secret.data["ca.crt"] == base64.b64encode(COREAPI_CA_CRT.encode("utf-8"))
    assert mock_v1_secrets.get.call_count == 1
    assert user_utils.core_internal_tls_secret.data["ca.crt"] == base64.b64encode(COREAPI_CA_CRT.encode("utf-8"))
    assert mock_v1_secrets.get.call_count == 1


def test_core_internal_ca_pem_file_path(user_utils, mock_named_temporary_file, mock_atexit):
    """
    Check the correct content is written to core_internal_ca_pem_file_path tempfile, that an exit handler is registered to
    delete the temp file, and that the tempfile is only written once (with its path cached)
    """
    assert str(user_utils.core_internal_ca_pem_file_path) == PEM_PATH
    assert mock_named_temporary_file.mock_calls == [
        call.write(COREAPI_CA_CRT.encode()),
        call.flush(),
        call.close(),
    ]
    assert mock_atexit.mock_calls == [call(os.remove, PEM_PATH)]

    # verify caching
    assert str(user_utils.core_internal_ca_pem_file_path) == PEM_PATH
    assert mock_named_temporary_file.mock_calls == [
        call.write(COREAPI_CA_CRT.encode()),
        call.flush(),
        call.close(),
    ]
    assert mock_atexit.mock_calls == [call(os.remove, PEM_PATH)]


def test_superuser_auth_token(user_utils, mock_logininitial_endpoint):
    assert mock_logininitial_endpoint.call_count == 0
    assert user_utils.superuser_auth_token == TOKEN
    assert mock_logininitial_endpoint.call_count == 1

    # verify caching
    user_utils.superuser_auth_token
    assert mock_logininitial_endpoint.call_count == 1


def test_manage_internal_tls_secret(user_utils, mock_v1_secrets):
    assert mock_v1_secrets.get.call_count == 0
    assert user_utils.manage_internal_tls_secret.data["ca.crt"] == base64.b64encode(MANAGE_CA_CRT.encode("utf-8"))
    assert user_utils.manage_internal_tls_secret.data["tls.crt"] == base64.b64encode(MANAGE_TLS_CRT.encode("utf-8"))
    assert user_utils.manage_internal_tls_secret.data["tls.key"] == base64.b64encode(MANAGE_TLS_KEY.encode("utf-8"))
    assert mock_v1_secrets.get.call_count == 1
    assert user_utils.manage_internal_tls_secret.data["ca.crt"] == base64.b64encode(MANAGE_CA_CRT.encode("utf-8"))
    assert user_utils.manage_internal_tls_secret.data["tls.crt"] == base64.b64encode(MANAGE_TLS_CRT.encode("utf-8"))
    assert user_utils.manage_internal_tls_secret.data["tls.key"] == base64.b64encode(MANAGE_TLS_KEY.encode("utf-8"))
    assert mock_v1_secrets.get.call_count == 1


def test_manage_internal_client_pem_file_path(user_utils, mock_named_temporary_file, mock_atexit):
    assert str(user_utils.manage_internal_client_pem_file_path) == PEM_PATH
    assert mock_named_temporary_file.mock_calls == [
        call.write(MANAGE_TLS_KEY.encode()),
        call.write(MANAGE_TLS_CRT.encode()),
        call.flush(),
        call.close(),
    ]
    assert mock_atexit.mock_calls == [call(os.remove, PEM_PATH)]

    # verify caching
    assert str(user_utils.manage_internal_client_pem_file_path) == PEM_PATH
    assert mock_named_temporary_file.mock_calls == [
        call.write(MANAGE_TLS_KEY.encode()),
        call.write(MANAGE_TLS_CRT.encode()),
        call.flush(),
        call.close(),
    ]
    assert mock_atexit.mock_calls == [call(os.remove, PEM_PATH)]


def test_manage_internal_ca_pem_file_path(user_utils, mock_named_temporary_file, mock_atexit):
    assert str(user_utils.manage_internal_ca_pem_file_path) == PEM_PATH
    assert mock_named_temporary_file.mock_calls == [
        call.write(MANAGE_CA_CRT.encode()),
        call.flush(),
        call.close(),
    ]
    assert mock_atexit.mock_calls == [call(os.remove, PEM_PATH)]

    # verify caching
    assert str(user_utils.manage_internal_ca_pem_file_path) == PEM_PATH
    assert mock_named_temporary_file.mock_calls == [
        call.write(MANAGE_CA_CRT.encode()),
        call.flush(),
        call.close(),
    ]
    assert mock_atexit.mock_calls == [call(os.remove, PEM_PATH)]


def test_mas_workspace_application_ids(user_utils, requests_mock):
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications",
        request_headers={"x-access-token": TOKEN},
        json=[{"id": "manage"}, {"id": "iot"}],
        status_code=200,
    )
    assert user_utils.mas_workspace_application_ids == ["manage", "iot"]
    assert get.call_count == 1

    # verify caching
    assert user_utils.mas_workspace_application_ids == ["manage", "iot"]
    assert get.call_count == 1


def test_mas_workspace_application_ids_filters_health(user_utils, requests_mock):
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications",
        request_headers={"x-access-token": TOKEN},
        json=[{"id": "manage"}, {"id": "health"}, {"id": "iot"}],
        status_code=200,
    )
    # health should be filtered out
    assert user_utils.mas_workspace_application_ids == ["manage", "iot"]
    assert get.call_count == 1


def test_get_user_exists(user_utils, requests_mock, mock_manage_api_key):
    user_id = "user1"
    get_core, get_manage, get_manage_personid = mock_get_user_200(requests_mock, user_id, mock_manage_api_key)
    resource_id, user_data = user_utils.get_user(user_id)
    # For version >= 9.1, Manage API uses "personid" and "displayname"
    # For version < 9.1, Core API uses "id" and "displayName"
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert user_data["personid"] == user_id
        assert user_data["displayname"] == user_id
    else:
        assert user_data["id"] == user_id
        assert user_data["displayName"] == user_id
    # For version >= 9.1, resource_id should be extracted; for < 9.1, it should be None
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert resource_id is not None
        assert resource_id == f"{user_id}_resource_id"
    else:
        assert resource_id is None

    # Check that the correct endpoint was called based on version
    if user_utils.mas_version >= "9.1":
        assert get_core.call_count == 0
        assert get_manage.call_count == 1
    else:
        assert get_core.call_count == 1
        assert get_manage.call_count == 0


def test_get_user_notfound(user_utils, requests_mock, mock_manage_api_key):
    user_id = "user1"
    get_core, get_manage, get_manage_personid = mock_get_user_404(requests_mock, user_id, mock_manage_api_key)
    resource_id, user_data = user_utils.get_user(user_id)
    assert resource_id is None
    assert user_data is None

    # Check that the correct endpoint was called based on version
    if user_utils.mas_version >= "9.1":
        assert get_core.call_count == 0
        assert get_manage.call_count == 1
    else:
        assert get_core.call_count == 1
        assert get_manage.call_count == 0


def test_get_user_error(user_utils, requests_mock, mock_manage_api_key):
    user_id = "user1"
    get_core, get_manage, get_manage_personid = mock_get_user_500(requests_mock, user_id, mock_manage_api_key)
    with pytest.raises(Exception):
        user_utils.get_user(user_id)

    # Check that the correct endpoint was called based on version
    if user_utils.mas_version >= "9.1":
        assert get_core.call_count == 0
        assert get_manage.call_count == 1
    else:
        assert get_core.call_count == 1
        assert get_manage.call_count == 0


def test_get_or_create_user_exists(user_utils, requests_mock, mock_manage_api_key):
    user_id = "user1"
    get_core, get_manage, get_manage_personid = mock_get_user_200(requests_mock, user_id, mock_manage_api_key)

    # Mock Core API endpoint for version < 9.1
    post_core = requests_mock.post(
        f"{MAS_API_URL}/v3/users",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=201,
        additional_matcher=lambda req: additional_matcher(req, json={"id": user_id}),
    )

    # Mock Manage API endpoint for version >= 9.1
    post_manage = requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/masperuser?lean=1",
        request_headers={"apikey": mock_manage_api_key["apikey"]},
        json={"id": user_id},
        status_code=201,
        additional_matcher=lambda req: additional_matcher(req, json={"personid": user_id}, cert=PEM_PATH),
    )

    # Use correct payload structure based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        payload = {"personid": user_id}
    else:
        payload = {"id": user_id}

    resource_id, user_data = user_utils.get_or_create_user(payload)
    # For version >= 9.1, Manage API uses "personid" and "displayname"
    # For version < 9.1, Core API uses "id" and "displayName"
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert user_data["personid"] == user_id
        assert user_data["displayname"] == user_id
    else:
        assert user_data["id"] == user_id
        assert user_data["displayName"] == user_id
    # For version >= 9.1, resource_id should be extracted; for < 9.1, it should be None
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert resource_id is not None
        assert resource_id == f"{user_id}_resource_id"
    else:
        assert resource_id is None
    # Check that the correct endpoint was called based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert get_core.call_count == 0
        assert get_manage.call_count == 1
    else:
        assert get_core.call_count == 1
        assert get_manage.call_count == 0
    assert post_core.call_count == 0
    assert post_manage.call_count == 0


def test_get_or_create_user_notfound(user_utils, requests_mock, mock_manage_api_key):
    user_id = "user1"
    get_core, get_manage, get_manage_personid = mock_get_user_404(requests_mock, user_id, mock_manage_api_key)

    # Mock Core API endpoint for version < 9.1
    post_core = requests_mock.post(
        f"{MAS_API_URL}/v3/users",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id, "displayName": user_id},
        status_code=201,
        additional_matcher=lambda req: additional_matcher(req, json={"id": user_id}),
    )

    # Mock Manage API endpoint for version >= 9.1
    post_manage = requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/masperuser?lean=1",
        request_headers={"apikey": mock_manage_api_key["apikey"]},
        json={"id": user_id, "displayName": user_id},
        status_code=201,
        additional_matcher=lambda req: additional_matcher(req, json={"personid": user_id}, cert=PEM_PATH),
    )

    # Use correct payload structure based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        payload = {"personid": user_id}
    else:
        payload = {"id": user_id}

    resource_id, user_data = user_utils.get_or_create_user(payload)
    assert user_data == {"id": user_id, "displayName": user_id}
    # For version >= 9.1, resource_id might be None if not in response; for < 9.1, it should be None
    if Version(user_utils.mas_version) < Version("9.1"):
        assert resource_id is None
    # Check that the correct endpoint was called based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert get_core.call_count == 0
        assert get_manage.call_count == 1
        assert post_core.call_count == 0
        assert post_manage.call_count == 1
    else:
        assert get_core.call_count == 1
        assert get_manage.call_count == 0
        assert post_core.call_count == 1
        assert post_manage.call_count == 0


def test_get_or_create_user_error(user_utils, requests_mock, mock_manage_api_key):
    user_id = "user1"
    get_core, get_manage, get_manage_personid = mock_get_user_404(requests_mock, user_id, mock_manage_api_key)

    # Mock Core API endpoint for version < 9.1
    post_core = requests_mock.post(
        f"{MAS_API_URL}/v3/users",
        request_headers={"x-access-token": TOKEN},
        json={"error": "unknown"},
        status_code=500,
        additional_matcher=lambda req: additional_matcher(req, json={"id": user_id}),
    )

    # Mock Manage API endpoint for version >= 9.1
    post_manage = requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/masperuser?lean=1",
        request_headers={"apikey": mock_manage_api_key["apikey"]},
        json={"error": "unknown"},
        status_code=500,
        additional_matcher=lambda req: additional_matcher(req, json={"personid": user_id}, cert=PEM_PATH),
    )

    # Use correct payload structure based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        payload = {"personid": user_id}
    else:
        payload = {"id": user_id}

    with pytest.raises(Exception):
        user_utils.get_or_create_user(payload)
    # Check that the correct endpoint was called based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert get_core.call_count == 0
        assert get_manage.call_count == 1
        assert post_core.call_count == 0
        assert post_manage.call_count == 1
    else:
        assert get_core.call_count == 1
        assert get_manage.call_count == 0
        assert post_core.call_count == 1
        assert post_manage.call_count == 0


def test_update_user(user_utils, requests_mock):
    user_id = "user1"
    put = requests_mock.put(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, json={"id": user_id}),
    )
    user_utils.update_user({"id": user_id})
    assert put.call_count == 1


def test_update_user_error(user_utils, requests_mock):
    user_id = "user1"
    put = requests_mock.put(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"error": "nofound"},
        status_code=404,
        additional_matcher=lambda req: additional_matcher(req, json={"id": user_id}),
    )
    with pytest.raises(Exception):
        user_utils.update_user({"id": user_id})
    assert put.call_count == 1


def test_update_user_display_name(user_utils, requests_mock):
    user_id = "user1"
    patche = requests_mock.patch(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, json={"displayName": "display_name"}),
    )
    user_utils.update_user_display_name(user_id, "display_name")
    assert patche.call_count == 1


def test_update_user_display_name_error(user_utils, requests_mock):
    user_id = "user1"
    patche = requests_mock.patch(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"error": "notfound"},
        status_code=404,
        additional_matcher=lambda req: additional_matcher(req, json={"displayName": "display_name"}),
    )
    with pytest.raises(Exception):
        user_utils.update_user_display_name(user_id, "display_name")
    assert patche.call_count == 1


def test_link_user_to_local_idp(user_utils, requests_mock, mock_manage_api_key):
    user_id = "user1"
    email_password = True
    resource_id = f"{user_id}_resource_id"
    get_core, get_manage, get_manage_personid = mock_get_user_200(requests_mock, user_id, mock_manage_api_key)

    # Mock Core API PUT request for version < 9.1
    put = requests_mock.put(
        f"{MAS_API_URL}/v3/users/{user_id}/idps/local?emailPassword={email_password}",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, json={"idpUserId": user_id}),
    )

    # Mock Manage API PATCH request for version >= 9.1
    patch = requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/masperuser/{resource_id}?lean=1&ccm=1",
        request_headers={
            "Content-Type": "application/json",
            "apikey": mock_manage_api_key["apikey"],
            "x-method-override": "PATCH",
            "patchtype": "MERGE",
        },
        json={"id": user_id},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(
            req,
            json={
                "maxuser": {
                    "userid": user_id,
                    "masuseridp": [
                        {
                            "emailpassword": True,
                            "idpid": "local",
                            "logintype": "0",
                            "idploginid": user_id,
                            "idptype": "local",
                            "enabled": True,
                        }
                    ],
                }
            },
            cert=PEM_PATH,
        ),
    )

    # Call the function with appropriate parameters based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        user_utils.link_user_to_local_idp(
            user_id,
            email_password=email_password,
            manage_api_key=mock_manage_api_key,
            resource_id=resource_id,
        )
    else:
        user_utils.link_user_to_local_idp(user_id, email_password=email_password)

    # Check that the correct endpoint was called based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert get_core.call_count == 0
        assert get_manage.call_count == 1
        assert put.call_count == 0
        assert patch.call_count == 1
    else:
        assert get_core.call_count == 1
        assert get_manage.call_count == 0
        assert put.call_count == 1
        assert patch.call_count == 0


def test_link_user_to_local_idp_usernotfound(user_utils, requests_mock, mock_manage_api_key):
    user_id = "user1"
    resource_id = f"{user_id}_resource_id"
    get_core, get_manage, get_manage_personid = mock_get_user_404(requests_mock, user_id, mock_manage_api_key)

    put = requests_mock.put(
        f"{MAS_API_URL}/v3/users/{user_id}/idps/local",
        additional_matcher=lambda req: additional_matcher(req, json={"idpUserId": user_id}),
    )

    patch = requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/masperuser/{resource_id}?lean=1&ccm=1",
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    with pytest.raises(Exception):
        if Version(user_utils.mas_version) >= Version("9.1"):
            user_utils.link_user_to_local_idp(user_id, manage_api_key=mock_manage_api_key, resource_id=resource_id)
        else:
            user_utils.link_user_to_local_idp(user_id)

    # Check that the correct endpoint was called based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert get_core.call_count == 0
        assert get_manage.call_count == 1
    else:
        assert get_core.call_count == 1
        assert get_manage.call_count == 0
    assert put.call_count == 0
    assert patch.call_count == 0


def test_link_user_to_local_idp_already_linked(user_utils, requests_mock, mock_manage_api_key):
    user_id = "user1"
    email_password = True
    resource_id = f"{user_id}_resource_id"
    get_core, get_manage, get_manage_personid = mock_get_user(
        requests_mock,
        user_id,
        {"id": user_id, "identities": {"_local": {}}},
        200,
        mock_manage_api_key,
        json_manage={
            "member": [
                {
                    "href": f"api/os/masperuser/{resource_id}",
                    "personid": user_id,
                    "displayname": user_id,
                    "identities": {"_local": {}},
                }
            ]
        },
    )

    put = requests_mock.put(
        f"{MAS_API_URL}/v3/users/{user_id}/idps/local?emailPassword={email_password}",
        request_headers={"x-access-token": TOKEN},
        json={"identities": {}},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, json={"idpUserId": user_id}),
    )

    patch = requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/masperuser/{resource_id}?lean=1&ccm=1",
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    # Call the function with appropriate parameters based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        user_utils.link_user_to_local_idp(
            user_id,
            email_password=email_password,
            manage_api_key=mock_manage_api_key,
            resource_id=resource_id,
        )
    else:
        user_utils.link_user_to_local_idp(user_id, email_password=email_password)

    # Check that the correct endpoint was called based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert get_core.call_count == 0
        assert get_manage.call_count == 1
    else:
        assert get_core.call_count == 1
        assert get_manage.call_count == 0
    assert put.call_count == 0
    assert patch.call_count == 0


def test_get_user_workspaces(user_utils, requests_mock):
    user_id = "user1"
    get = requests_mock.get(
        f"{MAS_API_URL}/v3/users/{user_id}/workspaces",
        request_headers={"x-access-token": TOKEN},
        json=[{"id": "masdev"}],
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )
    workspaces = user_utils.get_user_workspaces(user_id)
    assert workspaces == [{"id": "masdev"}]
    assert get.call_count == 1


def test_get_user_workspaces_usernotfound(user_utils, requests_mock):
    user_id = "user1"
    get = requests_mock.get(
        f"{MAS_API_URL}/v3/users/{user_id}/workspaces",
        request_headers={"x-access-token": TOKEN},
        json={},
        status_code=404,
        additional_matcher=lambda req: additional_matcher(req),
    )
    with pytest.raises(Exception):
        user_utils.get_user_workspaces(user_id)
    assert get.call_count == 1


def test_get_user_workspaces_error(user_utils, requests_mock):
    user_id = "user1"
    get = requests_mock.get(
        f"{MAS_API_URL}/v3/users/{user_id}/workspaces",
        request_headers={"x-access-token": TOKEN},
        json={"error": "internal"},
        status_code=500,
        additional_matcher=lambda req: additional_matcher(req),
    )
    with pytest.raises(Exception):
        user_utils.get_user_workspaces(user_id)
    assert get.call_count == 1


def test_add_user_to_workspace_already_a_member(user_utils, requests_mock):
    user_id = "user1"
    get = requests_mock.get(
        f"{MAS_API_URL}/v3/users/{user_id}/workspaces",
        request_headers={"x-access-token": TOKEN},
        json=[{"id": "someotherworkspace"}, {"id": MAS_WORKSPACE_ID}],
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )
    put = requests_mock.put(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json=[{"id": "masdev"}],
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, json={"permissions": {"workspaceAdmin": True}}),
    )
    user_utils.add_user_to_workspace(user_id, is_workspace_admin=True)
    assert get.call_count == 1
    assert put.call_count == 0


def test_add_user_to_workspace(user_utils, requests_mock):
    user_id = "user1"
    get = requests_mock.get(
        f"{MAS_API_URL}/v3/users/{user_id}/workspaces",
        request_headers={"x-access-token": TOKEN},
        json=[{"id": "someotherworkspace"}],
        status_code=200,
    )
    put = requests_mock.put(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, json={"permissions": {"workspaceAdmin": True}}),
    )
    user_utils.add_user_to_workspace(user_id, is_workspace_admin=True)
    assert get.call_count == 1
    assert put.call_count == 1


def test_add_user_to_workspace_error(user_utils, requests_mock):
    user_id = "user1"
    get = requests_mock.get(
        f"{MAS_API_URL}/v3/users/{user_id}/workspaces",
        request_headers={"x-access-token": TOKEN},
        json=[{"id": "someotherworkspace"}],
        status_code=200,
    )
    put = requests_mock.put(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"error": "internal"},
        status_code=500,
        additional_matcher=lambda req: additional_matcher(req, json={"permissions": {"workspaceAdmin": True}}),
    )
    with pytest.raises(Exception):
        user_utils.add_user_to_workspace(user_id, is_workspace_admin=True)
    assert get.call_count == 1
    assert put.call_count == 1


def test_get_user_application_permissions(user_utils, requests_mock):
    user_id = "user1"
    application_id = "manage"
    response_json = {
        "role": "USER",
        "userId": user_id,
        "workspaceId": MAS_WORKSPACE_ID,
        "userUrl": "https://api.yourmasdomain.com/users/joebloggs",
        "workspaceUrl": "https://api.yourmasdomain.com/workspaces/myworkspace1",
    }
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json=response_json,
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )
    assert user_utils.get_user_application_permissions(user_id, application_id) == response_json
    assert get.call_count == 1


def test_get_user_application_permissions_notfound(user_utils, requests_mock):
    user_id = "user1"
    application_id = "manage"
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"error": "notfound"},
        status_code=404,
        additional_matcher=lambda req: additional_matcher(req),
    )
    assert user_utils.get_user_application_permissions(user_id, application_id) is None
    assert get.call_count == 1


def test_get_user_application_permissions_error(user_utils, requests_mock):
    user_id = "user1"
    application_id = "manage"
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"error": "internal"},
        status_code=500,
        additional_matcher=lambda req: additional_matcher(req),
    )
    with pytest.raises(Exception):
        user_utils.get_user_application_permissions(user_id, application_id)
    assert get.call_count == 1


def test_set_user_application_permissions(user_utils, requests_mock):
    user_id = "user1"
    application_id = "manage"
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"error": "notfound"},
        status_code=404,
        additional_matcher=lambda req: additional_matcher(req),
    )
    put = requests_mock.put(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, json={"role": "USER"}),
    )
    user_utils.set_user_application_permission(user_id, application_id, "USER")
    assert get.call_count == 1
    assert put.call_count == 1


def test_set_user_application_permissions_alreadyset(user_utils, requests_mock):
    user_id = "user1"
    application_id = "manage"
    get_response_json = {
        "role": "ADMINISTRATOR",
        "userId": user_id,
        "workspaceId": MAS_WORKSPACE_ID,
        "userUrl": "https://api.yourmasdomain.com/users/joebloggs",
        "workspaceUrl": "https://api.yourmasdomain.com/workspaces/myworkspace1",
    }
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json=get_response_json,
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )
    put = requests_mock.put(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, json={"role": "USER"}),
    )
    user_utils.set_user_application_permission(user_id, application_id, "USER")
    assert get.call_count == 1
    assert put.call_count == 0


def test_resync_users(user_utils, requests_mock, mock_manage_api_key):
    user_ids = ["user1", "user2"]

    gets_core = []
    gets_manage = []
    patches = []
    for user_id in user_ids:
        get_core, get_manage, get_manage_personid = mock_get_user_200(requests_mock, user_id, mock_manage_api_key)
        gets_core.append(get_core)
        gets_manage.append(get_manage)

        patches.append(
            requests_mock.patch(
                f"{MAS_API_URL}/v3/users/{user_id}",
                request_headers={"x-access-token": TOKEN},
                json={"id": user_id},
                status_code=200,
                # uid=user_id captures the current value of user_id during each loop iteration, ensuring that the lambda uses the correct value when it is eventually called.
                additional_matcher=lambda req, uid=user_id: additional_matcher(req, json={"displayName": uid}),
            )
        )

    user_utils.resync_users(user_ids)

    # Check that the correct endpoint was called based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        for get_core in gets_core:
            assert get_core.call_count == 0
        for get_manage in gets_manage:
            assert get_manage.call_count == 1
    else:
        for get_core in gets_core:
            assert get_core.call_count == 1
        for get_manage in gets_manage:
            assert get_manage.call_count == 0

    for patche in patches:
        assert patche.call_count == 1


def test_check_user_sync(user_utils, requests_mock, mock_manage_api_key):
    # Skip for version >= 9.1 as Manage API doesn't return applications field
    if Version(user_utils.mas_version) >= Version("9.1"):
        pytest.skip("check_user_sync not applicable for version >= 9.1 (Manage API doesn't return applications field)")

    user_id = "user1"
    application_id = "manage"

    # transitions from PENDING -> SUCCESS on the third call
    attempts = 0

    def json_callback_core(request, context):
        nonlocal attempts
        # For version < 9.1, each get_user call makes 1 request
        if attempts >= 2:
            state = "SUCCESS"
        else:
            state = "PENDING"
        attempts = attempts + 1
        return {
            "id": user_id,
            "applications": {
                "other": {"sync": {"state": "ERROR"}},
                application_id: {"sync": {"state": state}},
            },
        }

    def json_callback_manage(request, context):
        nonlocal attempts
        # For version >= 9.1, each get_user call makes 2 requests
        attempts = attempts + 1
        resource_id = f"{user_id}_resource_id"
        # Manage API doesn't return applications field for version >= 9.1
        return {
            "member": [
                {
                    "href": f"api/os/masperuser/{resource_id}",
                    "personid": user_id,
                    "displayname": user_id,
                }
            ]
        }

    get_core, get_manage, get_manage_personid = mock_get_user(
        requests_mock,
        user_id,
        json_callback_core,
        200,
        mock_manage_api_key,
        json_manage=json_callback_manage,
    )

    user_utils.check_user_sync(user_id, application_id, timeout_secs=8, retry_interval_secs=0)

    # Check that the correct endpoint was called based on version
    # Note: For version >= 9.1, get_user makes 2 requests (query + resource_id GET)
    # but we only track the first query request in get_manage mock
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert get_core.call_count == 0
        # Each get_user call makes 2 requests, but we only count the query request
        assert get_manage.call_count == 3
    else:
        assert get_core.call_count == 3
        assert get_manage.call_count == 0


def test_check_user_sync_timeout(user_utils, requests_mock, mock_manage_api_key):
    # Skip for version >= 9.1 as Manage API doesn't return applications field
    if Version(user_utils.mas_version) >= Version("9.1"):
        pytest.skip("check_user_sync not applicable for version >= 9.1 (Manage API doesn't return applications field)")

    user_id = "user1"
    application_id = "manage"

    resource_id = f"{user_id}_resource_id"
    get_core, get_manage, get_manage_personid = mock_get_user(
        requests_mock,
        user_id,
        {
            "id": user_id,
            "applications": {
                "other": {"sync": {"state": "ERROR"}},
                application_id: {"sync": {"state": "PENDING"}},
            },
        },
        200,
        mock_manage_api_key,
        json_manage={
            "member": [
                {
                    "href": f"api/os/masperuser/{resource_id}",
                    "personid": user_id,
                    "displayname": user_id,
                }
            ]
        },
    )
    with pytest.raises(Exception) as excinfo:
        user_utils.check_user_sync(user_id, application_id, timeout_secs=0.3, retry_interval_secs=0.05)
    assert str(excinfo.value) == f"User {user_id} sync failed to complete for app within {0.3} seconds"

    # Check that the correct endpoint was called based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert get_core.call_count == 0
        assert get_manage.call_count > 1
    else:
        assert get_core.call_count > 1
        assert get_manage.call_count == 0


def test_check_user_sync_appstate_notfound(user_utils, requests_mock, mock_manage_api_key):
    # Skip for version >= 9.1 as Manage API doesn't return applications field
    if Version(user_utils.mas_version) >= Version("9.1"):
        pytest.skip("check_user_sync not applicable for version >= 9.1 (Manage API doesn't return applications field)")

    user_id = "user1"
    application_id = "manage"

    # first call (made bvy check_user_sync) returns user record with missing sync status for app
    # subsequent calls will include sync status and so should succeed
    # a single resync should have been triggered
    attempts = 0

    def json_callback_core(request, context):
        nonlocal attempts
        if attempts >= 1:
            ret = {
                "id": user_id,
                "displayName": user_id,
                "applications": {
                    "other": {"sync": {"state": "ERROR"}},
                    application_id: {"sync": {"state": "SUCCESS"}},
                },
            }
        else:
            ret = {
                "id": user_id,
                "displayName": user_id,
                "applications": {
                    "other": {"sync": {"state": "ERROR"}},
                },
            }
        attempts = attempts + 1
        return ret

    def json_callback_manage(request, context):
        nonlocal attempts
        resource_id = f"{user_id}_resource_id"
        # Manage API doesn't return applications field for version >= 9.1
        ret = {
            "member": [
                {
                    "href": f"api/os/masperuser/{resource_id}",
                    "personid": user_id,
                    "displayname": user_id,
                }
            ]
        }
        attempts = attempts + 1
        return ret

    patche = requests_mock.patch(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=200,
    )

    get_core, get_manage, get_manage_personid = mock_get_user(
        requests_mock,
        user_id,
        json_callback_core,
        200,
        mock_manage_api_key,
        json_manage=json_callback_manage,
    )

    user_utils.check_user_sync(user_id, application_id, timeout_secs=8, retry_interval_secs=0)

    # Check that the correct endpoint was called based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert get_core.call_count == 0
        # For version >= 9.1, each get_user call makes 2 requests
        assert get_manage.call_count == 3
        assert get_manage_personid.call_count == 3
    else:
        assert get_core.call_count == 3
        assert get_manage.call_count == 0

    # a single resync should have been triggered
    assert patche.call_count == 1


def test_check_user_sync_appstate_transient_error(user_utils, requests_mock, mock_manage_api_key):
    # Skip for version >= 9.1 as Manage API doesn't return applications field
    if Version(user_utils.mas_version) >= Version("9.1"):
        pytest.skip("check_user_sync not applicable for version >= 9.1 (Manage API doesn't return applications field)")

    user_id = "user1"
    application_id = "manage"

    # first call (made bvy check_user_sync) returns user record with sync state error
    # subsequent calls will have successful sync state and so should succeed
    # a single resync should have been triggered
    attempts = 0

    def json_callback_core(request, context):
        nonlocal attempts
        if attempts >= 1:
            ret = {
                "id": user_id,
                "displayName": user_id,
                "applications": {application_id: {"sync": {"state": "SUCCESS"}}},
            }
        else:
            ret = {
                "id": user_id,
                "displayName": user_id,
                "applications": {application_id: {"sync": {"state": "ERROR"}}},
            }
        attempts = attempts + 1
        return ret

    def json_callback_manage(request, context):
        nonlocal attempts
        resource_id = f"{user_id}_resource_id"
        # Manage API doesn't return applications field for version >= 9.1
        ret = {
            "member": [
                {
                    "href": f"api/os/masperuser/{resource_id}",
                    "personid": user_id,
                    "displayname": user_id,
                }
            ]
        }
        attempts = attempts + 1
        return ret

    patche = requests_mock.patch(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=200,
    )

    get_core, get_manage, get_manage_personid = mock_get_user(
        requests_mock,
        user_id,
        json_callback_core,
        200,
        mock_manage_api_key,
        json_manage=json_callback_manage,
    )

    user_utils.check_user_sync(user_id, application_id, timeout_secs=8, retry_interval_secs=0)

    # Check that the correct endpoint was called based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert get_core.call_count == 0
        # For version >= 9.1, each get_user call makes 2 requests
        assert get_manage.call_count == 3
        assert get_manage_personid.call_count == 3
    else:
        assert get_core.call_count == 3
        assert get_manage.call_count == 0

    # a single resync should have been triggered
    assert patche.call_count == 1


def test_check_user_sync_appstate_persistent_error(user_utils, requests_mock, mock_manage_api_key):
    user_id = "user1"
    application_id = "manage"

    patche = requests_mock.patch(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=200,
    )

    resource_id = f"{user_id}_resource_id"
    get_core, get_manage, get_manage_personid = mock_get_user(
        requests_mock,
        user_id,
        {
            "id": user_id,
            "displayName": user_id,
            "applications": {application_id: {"sync": {"state": "ERROR"}}},
        },
        200,
        mock_manage_api_key,
        json_manage={
            "member": [
                {
                    "href": f"api/os/masperuser/{resource_id}",
                    "personid": user_id,
                    "displayname": user_id,
                }
            ]
        },
    )

    with pytest.raises(Exception) as excinfo:
        user_utils.check_user_sync(user_id, application_id, timeout_secs=0.3, retry_interval_secs=0.05)
    assert str(excinfo.value) == f"User {user_id} sync failed to complete for app within {0.3} seconds"

    # Check that the correct endpoint was called based on version
    if Version(user_utils.mas_version) >= Version("9.1"):
        assert get_core.call_count == 0
        assert get_manage.call_count > 1
        # an "update_user_display_name" should have been triggered for every 2 get calls (1 call by check_user_sync, 1 by resync)
        assert patche.call_count == get_manage.call_count / 2
    else:
        assert get_core.call_count > 1
        assert get_manage.call_count == 0
        # an "update_user_display_name" should have been triggered for every 2 get calls (1 call by check_user_sync, 1 by resync)
        assert patche.call_count == get_core.call_count / 2


def test_get_manage_api_key_for_user_exists(user_utils, requests_mock):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }

    get = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1&oslc.select=*&oslc.where=userid="{user_id}"',
        request_headers={"accept": "application/json"},
        json={"member": [apikey]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    assert user_utils.get_manage_api_key_for_user(user_id) == apikey
    assert get.call_count == 1


def test_get_manage_api_key_for_user_notfound(user_utils, requests_mock):
    user_id = "user1"

    get = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1&oslc.select=*&oslc.where=userid="{user_id}"',
        request_headers={"accept": "application/json"},
        json={"member": []},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    assert user_utils.get_manage_api_key_for_user(user_id) is None
    assert get.call_count == 1


def test_get_manage_api_key_for_user_error(user_utils, requests_mock):
    user_id = "user1"

    get = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1&oslc.select=*&oslc.where=userid="{user_id}"',
        request_headers={"accept": "application/json"},
        text="boom",
        status_code=500,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    with pytest.raises(Exception) as excinfo:
        user_utils.get_manage_api_key_for_user(user_id)
    assert str(excinfo.value) == "500 boom"
    assert get.call_count == 1


@pytest.mark.parametrize("temporary", [(True), (False)])
def test_create_or_get_manage_api_key_for_user_new_api_key(temporary, user_utils, requests_mock, mock_atexit):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }

    post = requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1",
        request_headers={"content-type": "application/json"},
        json={"id": user_id},
        status_code=201,
        additional_matcher=lambda req: additional_matcher(req, json={"expiration": -1, "userid": user_id}, cert=PEM_PATH),
    )

    get = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1&oslc.select=*&oslc.where=userid="{user_id}"',
        request_headers={"accept": "application/json"},
        json={"member": [apikey]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    assert user_utils.create_or_get_manage_api_key_for_user(user_id, temporary=temporary) == apikey
    assert post.call_count == 1
    assert get.call_count == 1

    # if temporary, check we registered the exit hook to delete the temporary Manage API Key
    if temporary:
        assert (
            call(user_utils.delete_manage_api_key, apikey) in mock_atexit.mock_calls
        ), "delete_manage_api_key exit hook not registered for temporary api key that we created"
    else:
        assert (
            call(user_utils.delete_manage_api_key, apikey) not in mock_atexit.mock_calls
        ), "delete_manage_api_key exit hook registered unexpectedly for non-temporary api key that we created"


@pytest.mark.parametrize("temporary", [(True), (False)])
def test_create_or_get_manage_api_key_for_user_existing_api_key(temporary, user_utils, requests_mock, mock_atexit):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }

    post = requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1",
        request_headers={"content-type": "application/json"},
        json={"Error": {"reasonCode": "BMXAA10051E"}},
        status_code=400,
        additional_matcher=lambda req: additional_matcher(req, json={"expiration": -1, "userid": user_id}, cert=PEM_PATH),
    )

    get = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1&oslc.select=*&oslc.where=userid="{user_id}"',
        request_headers={"accept": "application/json"},
        json={"member": [apikey]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    assert user_utils.create_or_get_manage_api_key_for_user(user_id, temporary=temporary) == apikey
    assert post.call_count == 1
    assert get.call_count == 1

    # even if temporary is set, because we did not create the api key, we should not registered a hook to delete it
    assert (
        call(user_utils.delete_manage_api_key, apikey) not in mock_atexit.mock_calls
    ), "delete_manage_api_key exit hook registered unexpectedly for existing API Key that we did not create"


def test_create_or_get_manage_api_key_for_user_error(user_utils, requests_mock, mock_atexit):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }

    post = requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1",
        request_headers={"content-type": "application/json"},
        text="boom",
        status_code=400,
        additional_matcher=lambda req: additional_matcher(req, json={"expiration": -1, "userid": user_id}, cert=PEM_PATH),
    )

    get = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapiapikey?ccm=1&lean=1&oslc.select=*&oslc.where=userid="{user_id}"',
        request_headers={"accept": "application/json"},
        json={"member": [apikey]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    with pytest.raises(Exception) as excinfo:
        user_utils.create_or_get_manage_api_key_for_user(user_id, temporary=True)
    assert str(excinfo.value) == "400 boom"
    assert post.call_count == 1
    assert get.call_count == 0
    assert (
        call(user_utils.delete_manage_api_key, apikey) not in mock_atexit.mock_calls
    ), "delete_manage_api_key exit hook not registered even though we failed to create the api key"


def test_delete_manage_api_key(user_utils, requests_mock):
    user_id = "user1"
    apikey_id = "theapikeyid"
    apikey = {
        "userid": user_id,
        "href": f"https://{MANAGE_API_URL}:{MANAGE_API_PORT}/maximo/api/os/mxapiapikey/{apikey_id}",
    }

    delete = requests_mock.delete(
        f"{MANAGE_API_URL}/maximo/api/os/mxapiapikey/{apikey_id}?ccm=1&lean=1",
        request_headers={"accept": "application/json"},
        text="notused",
        status_code=204,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    user_utils.delete_manage_api_key(apikey)
    assert delete.call_count == 1


def test_delete_manage_api_key_notfound(user_utils, requests_mock):
    user_id = "user1"
    apikey_id = "theapikeyid"
    apikey = {
        "userid": user_id,
        "href": f"https://{MANAGE_API_URL}:{MANAGE_API_PORT}/maximo/api/os/mxapiapikey/{apikey_id}",
    }

    delete = requests_mock.delete(
        f"{MANAGE_API_URL}/maximo/api/os/mxapiapikey/{apikey_id}?ccm=1&lean=1",
        request_headers={"accept": "application/json"},
        text="notused",
        status_code=404,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    user_utils.delete_manage_api_key(apikey)
    assert delete.call_count == 1


def test_delete_manage_api_key_bad_href(user_utils, requests_mock):
    user_id = "user1"
    apikey_id = "theapikeyid"
    apikey = {"userid": user_id, "href": f"notgood/{apikey_id}"}

    delete = requests_mock.delete(
        f"{MANAGE_API_URL}/maximo/api/os/mxapiapikey/{apikey_id}?ccm=1&lean=1",
        request_headers={"accept": "application/json"},
        text="notused",
        status_code=204,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    with pytest.raises(Exception) as excinfo:
        user_utils.delete_manage_api_key(apikey)
    assert str(excinfo.value) == f"Could not parse API Key href: notgood/{apikey_id}"
    assert delete.call_count == 0


def test_delete_manage_api_key_error(user_utils, requests_mock):
    user_id = "user1"
    apikey_id = "theapikeyid"
    apikey = {
        "userid": user_id,
        "href": f"https://{MANAGE_API_URL}:{MANAGE_API_PORT}/maximo/api/os/mxapiapikey/{apikey_id}",
    }

    delete = requests_mock.delete(
        f"{MANAGE_API_URL}/maximo/api/os/mxapiapikey/{apikey_id}?ccm=1&lean=1",
        request_headers={"accept": "application/json"},
        text="boom",
        status_code=500,
        additional_matcher=lambda req: additional_matcher(req, cert=PEM_PATH),
    )

    with pytest.raises(Exception) as excinfo:
        user_utils.delete_manage_api_key(apikey)
    assert str(excinfo.value) == "500 boom"
    assert delete.call_count == 1


def test_get_manage_group_id(user_utils, requests_mock):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "apikey": "342fwasdasd",
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }  # pragma: allowlist secret
    group_name = "thegroup"
    group_id = "39231234"

    get = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup?ccm=1&lean=1&oslc.select=maxgroupid&oslc.where=groupname="{group_name}"',
        request_headers={"accept": "application/json", "apikey": apikey["apikey"]},
        json={"member": [{"maxgroupid": group_id}]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    assert user_utils.get_manage_group_id(group_name, apikey) == group_id
    assert get.call_count == 1


def test_get_manage_group_id_error(user_utils, requests_mock):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "apikey": "342fwasdasd",
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }  # pragma: allowlist secret
    group_name = "thegroup"

    get = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup?ccm=1&lean=1&oslc.select=maxgroupid&oslc.where=groupname="{group_name}"',
        request_headers={"accept": "application/json", "apikey": apikey["apikey"]},
        text="boom",
        status_code=500,
        additional_matcher=lambda req: additional_matcher(req),
    )
    with pytest.raises(Exception) as excinfo:
        user_utils.get_manage_group_id(group_name, apikey)
    assert str(excinfo.value) == "500 boom"
    assert get.call_count == 1


def test_get_manage_group_id_notfound(user_utils, requests_mock):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "apikey": "342fwasdasd",
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }  # pragma: allowlist secret
    group_name = "thegroup"

    get = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup?ccm=1&lean=1&oslc.select=maxgroupid&oslc.where=groupname="{group_name}"',
        request_headers={"accept": "application/json", "apikey": apikey["apikey"]},
        json={"member": [{}]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )
    assert user_utils.get_manage_group_id(group_name, apikey) is None
    assert get.call_count == 1


def test_is_user_in_manage_group_yes(user_utils, requests_mock):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "apikey": "342fwasdasd",
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }  # pragma: allowlist secret
    group_name = "thegroup"
    group_id = "39231234"

    get_group_id = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup?ccm=1&lean=1&oslc.select=maxgroupid&oslc.where=groupname="{group_name}"',
        request_headers={"accept": "application/json"},
        json={"member": [{"maxgroupid": group_id}], "apikey": apikey["apikey"]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    get_group_user = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup/{group_id}/groupuser?lean=1&oslc.where=userid="{user_id}"',
        request_headers={"accept": "application/json", "apikey": apikey["apikey"]},
        json={"member": [{}]},  # <--- member length non-empty indicates that the user is a member of the group
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    assert user_utils.is_user_in_manage_group(group_name, user_id, apikey)
    assert get_group_id.call_count == 1
    assert get_group_user.call_count == 1


def test_is_user_in_manage_group_no(user_utils, requests_mock):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "apikey": "342fwasdasd",
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }  # pragma: allowlist secret
    group_name = "thegroup"
    group_id = "39231234"

    get_group_id = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup?ccm=1&lean=1&oslc.select=maxgroupid&oslc.where=groupname="{group_name}"',
        request_headers={"accept": "application/json"},
        json={"member": [{"maxgroupid": group_id}], "apikey": apikey["apikey"]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    get_group_user = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup/{group_id}/groupuser?lean=1&oslc.where=userid="{user_id}"',
        request_headers={"accept": "application/json", "apikey": apikey["apikey"]},
        json={"member": []},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    assert not user_utils.is_user_in_manage_group(group_name, user_id, apikey)
    assert get_group_id.call_count == 1
    assert get_group_user.call_count == 1


def test_is_user_in_manage_group_error(user_utils, requests_mock):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "apikey": "342fwasdasd",
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }  # pragma: allowlist secret
    group_name = "thegroup"
    group_id = "39231234"

    get_group_id = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup?ccm=1&lean=1&oslc.select=maxgroupid&oslc.where=groupname="{group_name}"',
        request_headers={"accept": "application/json"},
        json={"member": [{"maxgroupid": group_id}], "apikey": apikey["apikey"]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    get_group_user = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup/{group_id}/groupuser?lean=1&oslc.where=userid="{user_id}"',
        request_headers={"accept": "application/json", "apikey": apikey["apikey"]},
        text="boom",
        status_code=500,
        additional_matcher=lambda req: additional_matcher(req),
    )

    with pytest.raises(Exception) as excinfo:
        user_utils.is_user_in_manage_group(group_name, user_id, apikey)
    assert str(excinfo.value) == "500 boom"
    assert get_group_id.call_count == 1
    assert get_group_user.call_count == 1


def test_is_user_in_manage_group_no_group_found(user_utils, requests_mock):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "apikey": "342fwasdasd",
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }  # pragma: allowlist secret
    group_name = "thegroup"
    group_id = "39231234"

    get_group_id = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup?ccm=1&lean=1&oslc.select=maxgroupid&oslc.where=groupname="{group_name}"',
        request_headers={"accept": "application/json"},
        json={"member": [], "apikey": apikey["apikey"]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    get_group_user = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup/{group_id}/groupuser?lean=1&oslc.where=userid="{user_id}"',
        request_headers={"accept": "application/json", "apikey": apikey["apikey"]},
        text="boom",
        status_code=500,
        additional_matcher=lambda req: additional_matcher(req),
    )

    with pytest.raises(Exception) as excinfo:
        user_utils.is_user_in_manage_group(group_name, user_id, apikey)
    assert str(excinfo.value) == f"No Manage group found with name {group_name}"
    assert get_group_id.call_count == 1
    assert get_group_user.call_count == 0


def test_add_user_to_manage_group(user_utils, requests_mock):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "apikey": "342fwasdasd",
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }  # pragma: allowlist secret
    group_name = "thegroup"
    group_id = "39231234"

    get_group_id = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup?ccm=1&lean=1&oslc.select=maxgroupid&oslc.where=groupname="{group_name}"',
        request_headers={"accept": "application/json"},
        json={"member": [{"maxgroupid": group_id}], "apikey": apikey["apikey"]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    get_group_user = requests_mock.get(
        f"{MANAGE_API_URL}/maximo/api/os/mxapigroup/{group_id}/groupuser?lean=1",
        request_headers={"accept": "application/json", "apikey": apikey["apikey"]},
        json={"member": []},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    add_group_user = requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/mxapigroup/{group_id}",
        request_headers={
            "accept": "application/json",
            "content-type": "application/json",
            "x-method-override": "PATCH",
            "patchtype": "MERGE",
            "apikey": apikey["apikey"],
        },
        json={},
        status_code=204,
        additional_matcher=lambda req: additional_matcher(req, json={"groupuser": [{"userid": user_id}]}),
    )

    assert user_utils.add_user_to_manage_group(user_id, group_name, apikey) is None
    assert get_group_id.call_count == 2
    assert get_group_user.call_count == 1
    assert add_group_user.call_count == 1


def test_add_user_to_manage_group_already_member(user_utils, requests_mock):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "apikey": "342fwasdasd",
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }  # pragma: allowlist secret
    group_name = "thegroup"
    group_id = "39231234"

    get_group_id = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup?ccm=1&lean=1&oslc.select=maxgroupid&oslc.where=groupname="{group_name}"',
        request_headers={"accept": "application/json"},
        json={"member": [{"maxgroupid": group_id}], "apikey": apikey["apikey"]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    get_group_user = requests_mock.get(
        f"{MANAGE_API_URL}/maximo/api/os/mxapigroup/{group_id}/groupuser?lean=1",
        request_headers={"accept": "application/json", "apikey": apikey["apikey"]},
        json={"member": [{}]},  # <--- member length non-empty indicates that the user is a member of the group
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    add_group_user = requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/mxapigroup/{group_id}",
        request_headers={
            "accept": "application/json",
            "content-type": "application/json",
            "x-method-override": "PATCH",
            "patchtype": "MERGE",
            "apikey": apikey["apikey"],
        },
        json={},
        status_code=204,
        additional_matcher=lambda req: additional_matcher(req, json={"groupuser": [{"userid": user_id}]}),
    )

    assert user_utils.add_user_to_manage_group(user_id, group_name, apikey) is None
    assert get_group_id.call_count == 1
    assert get_group_user.call_count == 1
    assert add_group_user.call_count == 0


def test_add_user_to_manage_group_error(user_utils, requests_mock):
    user_id = "user1"
    apikey = {
        "userid": user_id,
        "apikey": "342fwasdasd",
        "href": f"https://{MANAGE_API_URL}/maximo/api/os/mxapikey/theapikeyid",
    }  # pragma: allowlist secret
    group_name = "thegroup"
    group_id = "39231234"

    get_group_id = requests_mock.get(
        f'{MANAGE_API_URL}/maximo/api/os/mxapigroup?ccm=1&lean=1&oslc.select=maxgroupid&oslc.where=groupname="{group_name}"',
        request_headers={"accept": "application/json"},
        json={"member": [{"maxgroupid": group_id}], "apikey": apikey["apikey"]},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    get_group_user = requests_mock.get(
        f"{MANAGE_API_URL}/maximo/api/os/mxapigroup/{group_id}/groupuser?lean=1",
        request_headers={"accept": "application/json", "apikey": apikey["apikey"]},
        json={"member": []},
        status_code=200,
        additional_matcher=lambda req: additional_matcher(req),
    )

    add_group_user = requests_mock.post(
        f"{MANAGE_API_URL}/maximo/api/os/mxapigroup/{group_id}",
        request_headers={
            "accept": "application/json",
            "content-type": "application/json",
            "x-method-override": "PATCH",
            "patchtype": "MERGE",
            "apikey": apikey["apikey"],
        },
        text="boom",
        status_code=500,
        additional_matcher=lambda req: additional_matcher(req, json={"groupuser": [{"userid": user_id}]}),
    )
    with pytest.raises(Exception) as excinfo:
        user_utils.add_user_to_manage_group(user_id, group_name, apikey)
    assert str(excinfo.value) == "500 boom"
    assert get_group_id.call_count == 2
    assert get_group_user.call_count == 1
    assert add_group_user.call_count == 1


def test_get_mas_applications_in_workspace(user_utils, requests_mock):
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications",
        request_headers={"x-access-token": TOKEN},
        json=[{"id": "manage"}],
        status_code=200,
    )
    assert user_utils.get_mas_applications_in_workspace() == [{"id": "manage"}]
    assert get.call_count == 1


def test_get_mas_applications_in_workspace_error(user_utils, requests_mock):
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications",
        request_headers={"x-access-token": TOKEN},
        json={"error": "internal"},
        status_code=500,
    )
    with pytest.raises(Exception) as excinfo:
        user_utils.get_mas_applications_in_workspace()
    assert get.call_count == 1
    assert str(excinfo.value) == '500 {"error": "internal"}'


def test_get_mas_application_availability(user_utils, requests_mock):
    application_id = "manage"
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}",
        request_headers={"x-access-token": TOKEN},
        json={"id": "manage"},
        status_code=200,
    )
    assert user_utils.get_mas_application_availability(application_id) == {"id": "manage"}
    assert get.call_count == 1


def test_get_mas_application_availability_error(user_utils, requests_mock):
    application_id = "manage"
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}",
        request_headers={"x-access-token": TOKEN},
        json={"error": "internal"},
        status_code=500,
    )
    with pytest.raises(Exception) as excinfo:
        user_utils.get_mas_application_availability(application_id)
    assert get.call_count == 1
    assert str(excinfo.value) == '500 {"error": "internal"}'


def test_await_mas_application_availability(user_utils, requests_mock):
    application_id = "manage"

    # returns all possible permutations of the endpoint, until finally returning the
    # response that should cause the retry logic to exit
    return_values = [
        {
            "id": application_id,
        },
        {
            "available": False,
        },
        {
            "available": True,
        },
        {
            "ready": False,
        },
        {
            "ready": True,
        },
        {
            "available": False,
            "ready": False,
        },
        {
            "available": True,
            "ready": False,
        },
        {
            "available": False,
            "ready": True,
        },
        {
            "available": True,
            "ready": True,
        },
    ]
    attempt = 0

    def json_callback(request, context):
        nonlocal attempt
        ret = return_values[attempt]
        attempt = attempt + 1
        return ret

    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}",
        request_headers={"x-access-token": TOKEN},
        json=json_callback,
        status_code=200,
    )

    user_utils.await_mas_application_availability(application_id, timeout_secs=5, retry_interval_secs=0)
    assert get.call_count == len(return_values)


def test_await_mas_application_availability_timeout(user_utils, requests_mock):
    application_id = "manage"

    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}",
        request_headers={"x-access-token": TOKEN},
        json={
            "available": False,
            "ready": False,
        },
        status_code=200,
    )

    with pytest.raises(Exception) as excinfo:
        user_utils.await_mas_application_availability(application_id, timeout_secs=1, retry_interval_secs=0.1)
    assert get.call_count > 1
    assert str(excinfo.value) == f"{application_id} did not become ready and available in time, aborting"


def test_parse_initial_users_from_aws_secret_json(user_utils):

    actual_initial_users = user_utils.parse_initial_users_from_aws_secret_json(
        {
            "user1@example.com": "primary,joe,bloggs",
            "user2@example.com": "  primary     ,   ben     ,   bob  ",
            "user3@example.com": "secondary     ,bill,  bibb",
            "user4@example.com": "primary     ,bab,  bub,user4",
        }
    )

    expected_initial_users = {
        "users": {
            "primary": [
                {
                    "email": "user1@example.com",
                    "given_name": "joe",
                    "family_name": "bloggs",
                    "id": "user1@example.com",
                },
                {
                    "email": "user2@example.com",
                    "given_name": "ben",
                    "family_name": "bob",
                    "id": "user2@example.com",
                },
                {
                    "email": "user4@example.com",
                    "given_name": "bab",
                    "family_name": "bub",
                    "id": "user4",
                },
            ],
            "secondary": [
                {
                    "email": "user3@example.com",
                    "given_name": "bill",
                    "family_name": "bibb",
                    "id": "user3@example.com",
                }
            ],
        }
    }

    assert actual_initial_users == expected_initial_users

    with pytest.raises(Exception) as excinfo:
        user_utils.parse_initial_users_from_aws_secret_json({"user1@example.com": "primary"})
    assert "Wrong number of CSV values for user1@example.com (expected 3 or 4 but got 1)" == str(excinfo.value)

    with pytest.raises(Exception) as excinfo:
        user_utils.parse_initial_users_from_aws_secret_json({"user1@example.com": "unknown,x,y"})
    assert "Unknown user type for user1@example.com: unknown" == str(excinfo.value)


def test_create_initial_user_for_saas_no_email(user_utils):
    with pytest.raises(Exception) as excinfo:
        user_utils.create_initial_user_for_saas({"given_name": "asdasd", "family_name": "sdfzsd"}, None)
    assert str(excinfo.value) == "'email' not found in at least one of the user defs"


def test_create_initial_user_for_saas_no_given_name(user_utils):
    with pytest.raises(Exception) as excinfo:
        user_utils.create_initial_user_for_saas({"email": "asda", "family_name": "sdfzsd"}, None)
    assert str(excinfo.value) == "'given_name' not found in at least one of the user defs"


def test_create_initial_user_for_saas_no_family_name(user_utils):
    with pytest.raises(Exception) as excinfo:
        user_utils.create_initial_user_for_saas({"email": "asda", "given_name": "asdasd"}, None)
    assert str(excinfo.value) == "'family_name' not found in at least one of the user defs"


def test_create_initial_user_for_saas_unsupported_type(user_utils):
    with pytest.raises(Exception) as excinfo:
        user_utils.create_initial_user_for_saas(
            {"given_name": "asdasd", "family_name": "sdfzsd", "email": "asdasd"},
            "whoknows",
        )
    assert str(excinfo.value) == "Unsupported user_type: whoknows"


# Assisted by watsonx Code Assistant


@pytest.mark.parametrize(
    "user_type, user_id, user_email, is_workspace_admin, application_role, manage_role, facilities_role, manage_security_groups_90, manage_security_groups_91",
    [
        (
            "PRIMARY",
            None,
            "bill.bob@acme.com",
            True,
            "ADMIN",
            "MANAGEUSER",
            "PREMIUM",
            ["MAXADMIN"],
            ["USERMANAGEMENT"],
        ),
        (
            "PRIMARY",
            "billbob",
            "bill.bob@acme.com",
            True,
            "ADMIN",
            "MANAGEUSER",
            "PREMIUM",
            ["MAXADMIN"],
            ["USERMANAGEMENT"],
        ),
        (
            "SECONDARY",
            None,
            "bab.bon@acme.com",
            False,
            "USER",
            "MANAGEUSER",
            "BASE",
            [],
            [],
        ),
        (
            "SECONDARY",
            "babbon",
            "bab.bon@acme.com",
            False,
            "USER",
            "MANAGEUSER",
            "BASE",
            [],
            [],
        ),
    ],
)
def test_create_initial_user_for_saas(
    user_type,
    user_id,
    user_email,
    is_workspace_admin,
    application_role,
    manage_role,
    facilities_role,
    manage_security_groups_90,
    manage_security_groups_91,
    user_utils,
    requests_mock,
):
    # Determine expected values based on MAS version
    mas_version = user_utils.mas_version
    if mas_version == "9.0":
        manage_security_groups = manage_security_groups_90
        if user_type == "PRIMARY":
            permissions = {
                "systemAdmin": False,
                "userAdmin": True,
                "apikeyAdmin": False,
            }
            entitlement = {
                "application": "PREMIUM",
                "admin": "ADMIN_BASE",
                "alwaysReserveLicense": True,
            }
        else:  # SECONDARY
            permissions = {
                "systemAdmin": False,
                "userAdmin": False,
                "apikeyAdmin": False,
            }
            entitlement = {
                "application": "BASE",
                "admin": "NONE",
                "alwaysReserveLicense": True,
            }
    else:  # 9.1
        manage_security_groups = manage_security_groups_91
        permissions = None  # Not used in 9.1
        entitlement = None  # Not used in 9.1
    # Mock get_or_create_user to return appropriate response based on version
    # Note: user_id might be None at this point, it gets set to user_email later
    actual_user_id = user_id if user_id is not None else user_email
    if Version(mas_version) >= Version("9.1"):
        # For 9.1, return tuple (resource_id, user_data) with member array containing href
        resource_id = f"_{actual_user_id.replace('@', '_').replace('.', '_')}_resource_id"
        user_utils.get_or_create_user = MagicMock(
            return_value=(
                resource_id,
                {
                    "member": [{"href": f"api/os/masperuser/{resource_id}"}],
                    "id": actual_user_id,
                },
            )
        )
    else:
        # For version < 9.1, return tuple (None, user_data)
        user_utils.get_or_create_user = MagicMock(return_value=(None, {"id": actual_user_id}))
    user_utils.link_user_to_local_idp = MagicMock()
    user_utils.add_user_to_workspace = MagicMock()
    mas_workspace_application_ids = ["manage", "iot", "facilities"]
    user_utils.get_mas_applications_in_workspace = MagicMock(return_value=list(map(lambda x: {"id": x}, mas_workspace_application_ids)))
    user_utils.await_mas_application_availability = MagicMock()
    user_utils.set_user_application_permission = MagicMock()
    user_utils.check_user_sync = MagicMock()
    manage_api_key = "manage_api_key"  # pragma: allowlist secret
    user_utils.create_or_get_manage_api_key_for_user = MagicMock(return_value=manage_api_key)
    user_utils.add_user_to_manage_group = MagicMock()
    user_utils.set_user_group_reassignment_auth = MagicMock()

    user_given_name = "billy"
    user_family_name = "bobby"
    display_name = f"{user_given_name} {user_family_name}"

    initial_users = {
        "email": user_email,
        "given_name": user_given_name,
        "family_name": user_family_name,
    }

    if user_id is None:
        user_id = user_email
    else:
        initial_users["id"] = user_id

    username = user_id

    # For version 9.1 PRIMARY users, pass groupreassign parameter
    if Version(mas_version) >= Version("9.1") and user_type == "PRIMARY":
        groupreassign = [{"groupname": "USERMANAGEMENT"}]
        user_utils.create_initial_user_for_saas(initial_users, user_type, groupreassign)
    else:
        user_utils.create_initial_user_for_saas(initial_users, user_type)

    # Build expected user_def based on version
    if mas_version == "9.0":
        expected_user_def = {
            "id": user_id,
            "status": {"active": True},
            "username": username,
            "owner": "local",
            "emails": [{"value": user_email, "type": "Work", "primary": True}],
            "phoneNumbers": [],
            "addresses": [],
            "displayName": display_name,
            "issuer": "local",
            "permissions": permissions,
            "entitlement": entitlement,
            "givenName": user_given_name,
            "familyName": user_family_name,
        }
    else:  # >=9.1
        if user_type == "PRIMARY":
            maxuser_def = {
                "userid": user_id,
                "personid": user_id,
                "loginid": user_id,
                "owner": "local",
                "systemadmin": False,
                "apikeyadmin": True,
                "isauthorized": 1,
                "idpadmin": True,
                "status": "ACTIVE",
                "groupuser": [{"groupname": "USERMANAGEMENT"}],
            }
        else:  # SECONDARY
            maxuser_def = {
                "userid": user_id,
                "personid": user_id,
                "loginid": user_id,
                "owner": "local",
                "systemadmin": False,
                "apikeyadmin": False,
                "isauthorized": 0,
                "idpadmin": False,
                "status": "ACTIVE",
            }

        expected_user_def = {
            "personid": user_id,
            "primaryemailtype": "Work",
            "primaryemail": user_email,
            "primaryphone": "",
            "addressline1": "",
            "displayName": display_name,
            "maxuser": maxuser_def,
        }

    user_utils.get_or_create_user.assert_called_once_with(expected_user_def)

    # Check link_user_to_local_idp call based on version
    if Version(mas_version) >= Version("9.1"):
        resource_id = f"_{actual_user_id.replace('@', '_').replace('.', '_')}_resource_id"
        user_utils.link_user_to_local_idp.assert_called_once_with(
            user_id,
            email_password=True,
            manage_api_key=manage_api_key,
            resource_id=resource_id,
        )
    else:
        user_utils.link_user_to_local_idp.assert_called_once_with(user_id, email_password=True)
        user_utils.add_user_to_workspace.assert_called_once_with(user_id, is_workspace_admin=is_workspace_admin)

    # For version < 9.1, await_mas_application_availability and set_user_application_permission are called
    # For version >= 9.1, they are NOT called
    if mas_version == "9.0":
        user_utils.await_mas_application_availability.assert_has_calls([call("manage"), call("iot")])
        user_utils.set_user_application_permission.assert_has_calls(
            [
                call(user_id, "manage", manage_role),
                call(user_id, "iot", application_role),
                call(user_id, "facilities", facilities_role),
            ]
        )
    else:  # >=9.1
        user_utils.await_mas_application_availability.assert_not_called()
        user_utils.set_user_application_permission.assert_not_called()

    # check_user_sync is only called for version < 9.1
    # For version >= 9.1, Manage API doesn't return applications field, so sync check is not performed
    if mas_version == "9.0":
        user_utils.check_user_sync.assert_has_calls([call(user_id, "manage"), call(user_id, "iot"), call(user_id, "facilities")])
    else:  # 9.1
        user_utils.check_user_sync.assert_not_called()

    # For version >= 9.1, API key is always created (needed for link_user_to_local_idp)
    # For version < 9.1, API key is only created if there are manage_security_groups
    if Version(mas_version) >= Version("9.1") or len(manage_security_groups) > 0:
        user_utils.create_or_get_manage_api_key_for_user.assert_called_once_with("MXINTADM", temporary=True)
    else:
        user_utils.create_or_get_manage_api_key_for_user.assert_not_called()

    if len(manage_security_groups) > 0:
        # For version < 9.1, add_user_to_manage_group is called
        # For version >= 9.1, set_user_group_reassignment_auth is called for PRIMARY users
        if mas_version == "9.0":
            user_utils.add_user_to_manage_group.assert_has_calls(
                list(
                    map(
                        lambda sg: call(user_id, sg, manage_api_key),
                        manage_security_groups,
                    )
                )
            )
            user_utils.set_user_group_reassignment_auth.assert_not_called()
        else:  # >=9.1
            user_utils.add_user_to_manage_group.assert_not_called()
            if user_type == "PRIMARY":
                # For versions >= 9.1, both user_id and resource_id are passed
                actual_user_id = user_id if user_id is not None else user_email
                resource_id = f"_{actual_user_id.replace('@', '_').replace('.', '_')}_resource_id"
                user_utils.set_user_group_reassignment_auth.assert_called_once_with(
                    actual_user_id,
                    resource_id,
                    [{"groupname": "USERMANAGEMENT"}],
                    manage_api_key,
                )
            else:
                user_utils.set_user_group_reassignment_auth.assert_not_called()


def test_create_initial_users_for_saas_invalid_inputs(user_utils):
    with pytest.raises(Exception) as excinfo:
        user_utils.create_initial_users_for_saas({})
    assert str(excinfo.value) == "expected top-level key 'users' not found"

    with pytest.raises(Exception) as excinfo:
        user_utils.create_initial_users_for_saas({"users": {}})
    assert str(excinfo.value) == "expected key 'users.primary' not found"

    with pytest.raises(Exception) as excinfo:
        user_utils.create_initial_users_for_saas({"users": {"primary": "nope"}})
    assert str(excinfo.value) == "'users.primary' is not a list"

    with pytest.raises(Exception) as excinfo:
        user_utils.create_initial_users_for_saas({"users": {"primary": []}})
    assert str(excinfo.value) == "expected key 'users.secondary' not found"

    with pytest.raises(Exception) as excinfo:
        user_utils.create_initial_users_for_saas({"users": {"primary": [], "secondary": "nope"}})
    assert str(excinfo.value) == "'users.secondary' is not a list"


def test_create_initial_users_for_saas_no_users(user_utils):
    assert user_utils.create_initial_users_for_saas({"users": {"primary": [], "secondary": []}}) == {"completed": [], "failed": []}


def test_create_initial_users_for_saas(user_utils):

    mas_workspace_application_ids = ["manage", "iot"]
    user_utils.get_mas_applications_in_workspace = MagicMock(return_value=map(lambda x: {"id": x}, mas_workspace_application_ids))
    user_utils.await_mas_application_availability = MagicMock()
    user_utils.get_all_manage_groups = MagicMock(return_value=["MAXADMIN", "MAXUSER"])
    user_utils.create_initial_user_for_saas = MagicMock()

    def fail_for_users_b_and_e(user, user_type, groupreassign=None):
        if user["email"] in ["b", "e"]:
            raise Exception(f"{user['email']} should fail")

    user_utils.create_initial_user_for_saas.side_effect = fail_for_users_b_and_e

    initial_users = {
        "users": {
            "primary": [{"email": "a"}, {"email": "b"}, {"email": "c"}],
            "secondary": [{"email": "d"}, {"email": "e"}, {"email": "f"}],
        }
    }

    assert user_utils.create_initial_users_for_saas(initial_users) == {
        "completed": [
            {"email": "a"},
            {"email": "c"},
            {"email": "d"},
            {"email": "f"},
        ],
        "failed": [
            {"email": "b"},
            {"email": "e"},
        ],
    }

    user_utils.await_mas_application_availability.assert_has_calls([call("manage"), call("iot")])
