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
from unittest.mock import MagicMock, patch
from pytest import fixture

from mas.devops.users import MASUserUtils


TOKEN = "TOKEN"
MAS_INSTANCE_ID = "inst1"
MAS_WORKSPACE_ID = "masdev"

MAS_CORE_NAMESPACE = f"mas-{MAS_INSTANCE_ID}-core"
MANAGE_NAMESPACE = f"mas-{MAS_INSTANCE_ID}-manage"

ADMIN_DASHBOARD_PORT = 1
COREAPI_PORT = 2

MAS_ADMIN_URL = f"https://admin-dashboard.{MAS_CORE_NAMESPACE}.svc.cluster.local:{ADMIN_DASHBOARD_PORT}"
MAS_API_URL = f'https://coreapi.{MAS_CORE_NAMESPACE}.svc.cluster.local:{COREAPI_PORT}'


def get_secret(name, namespace):
    if name.endswith("-credentials-superuser"):
        data = {
            "username": base64.b64encode("hello".encode("utf-8")),
            "password": base64.b64encode("world".encode("utf-8")),
        }

    if name.endswith("-admindashboard-cert-internal"):
        data = {
            "ca.crt": base64.b64encode("admindashboard-ca".encode("utf-8"))
        }

    if name.endswith("-coreapi-cert-internal"):
        data = {
            "ca.crt": base64.b64encode("coreapi-ca".encode("utf-8"))
        }

    return MagicMock(
        data=data
    )


@fixture
def mock_v1_secrets():
    with patch('mas.devops.users.DynamicClient') as mock_DynamicClientCls:
        mock_DynamicClient = mock_DynamicClientCls.return_value
        mock_v1_secrets = mock_DynamicClient.resources.get.return_value
        mock_v1_secrets.get.side_effect = get_secret
        yield


@fixture
def user_utils(mock_v1_secrets, requests_mock):
    user_utils = MASUserUtils(
        MAS_INSTANCE_ID,
        MAS_WORKSPACE_ID,
        None,
        coreapi_port=COREAPI_PORT,
        admin_dashboard_port=ADMIN_DASHBOARD_PORT
    )
    get_token = requests_mock.post(f"{MAS_ADMIN_URL}/logininitial", json=dict(token=TOKEN))
    assert get_token.call_count == 0
    yield user_utils

    # assuming the test calls any MAS Core API (all do)
    # we expect the token endpoint to have been called exactly once (and its response cached)
    assert get_token.call_count == 1


def mock_get_user(requests_mock, user_id, json, status_code):
    return requests_mock.get(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json=json,
        status_code=status_code
    )


def mock_get_user_200(requests_mock, user_id):
    return mock_get_user(
        requests_mock, user_id, {"id": user_id}, 200
    )


def mock_get_user_404(requests_mock, user_id):
    return mock_get_user(
        requests_mock, user_id, {"error": "notfound"}, 404
    )


def mock_get_user_500(requests_mock, user_id):
    return mock_get_user(
        requests_mock, user_id, {"error": "internal"}, 500
    )


def test_get_user_exists(user_utils, requests_mock):
    user_id = "user1"
    get = mock_get_user_200(requests_mock, user_id)
    assert user_utils.get_user(user_id) == {"id": user_id}
    assert get.call_count == 1


def test_get_user_notfound(user_utils, requests_mock):
    user_id = "user1"
    get = mock_get_user_404(requests_mock, user_id)
    assert user_utils.get_user(user_id) is None
    assert get.call_count == 1


def test_get_user_error(user_utils, requests_mock):
    user_id = "user1"
    get = mock_get_user_500(requests_mock, user_id)
    with pytest.raises(Exception):
        user_utils.get_user(user_id)
    assert get.call_count == 1


def test_get_or_create_user_exists(user_utils, requests_mock):
    user_id = "user1"
    get = mock_get_user_200(requests_mock, user_id)

    post = requests_mock.post(
        f"{MAS_API_URL}/v3/users",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=201
    )

    assert user_utils.get_or_create_user({"id": user_id}) == {"id": user_id}
    assert get.call_count == 1
    assert post.call_count == 0


def test_get_or_create_user_notfound(user_utils, requests_mock):
    user_id = "user1"
    get = mock_get_user_404(requests_mock, user_id)

    post = requests_mock.post(
        f"{MAS_API_URL}/v3/users",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=201
    )

    assert user_utils.get_or_create_user({"id": user_id}) == {"id": user_id}
    assert get.call_count == 1
    assert post.call_count == 1


def test_get_or_create_user_error(user_utils, requests_mock):
    user_id = "user1"
    get = mock_get_user_404(requests_mock, user_id)
    post = requests_mock.post(
        f"{MAS_API_URL}/v3/users",
        request_headers={"x-access-token": TOKEN},
        json={"error": "unknown"},
        status_code=500
    )

    with pytest.raises(Exception):
        user_utils.get_or_create_user({"id": user_id})
    assert get.call_count == 1
    assert post.call_count == 1


def test_link_user_to_local_idp(user_utils, requests_mock):
    user_id = "user1"
    email_password = True
    get = mock_get_user_200(requests_mock, user_id)

    put = requests_mock.put(
        f"{MAS_API_URL}/v3/users/{user_id}/idps/local?emailPassword={email_password}",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=200
    )

    user_utils.link_user_to_local_idp(user_id, email_password=email_password)

    assert get.call_count == 1
    assert put.call_count == 1


def test_link_user_to_local_idp_usernotfound(user_utils, requests_mock):
    user_id = "user1"
    get = mock_get_user_404(requests_mock, user_id)
    put = requests_mock.put(
        f"{MAS_API_URL}/v3/users/{user_id}/idps/local",
    )

    with pytest.raises(Exception):
        user_utils.link_user_to_local_idp(user_id)

    assert get.call_count == 1
    assert put.call_count == 0


def test_link_user_to_local_idp_already_linked(user_utils, requests_mock):
    user_id = "user1"
    email_password = True
    get = mock_get_user(
        requests_mock, user_id, {"id": user_id, "identities": {"_local": {}}}, 200
    )

    put = requests_mock.put(
        f"{MAS_API_URL}/v3/users/{user_id}/idps/local?emailPassword={email_password}",
        request_headers={"x-access-token": TOKEN},
        json={"identities": {}},
        status_code=200
    )

    user_utils.link_user_to_local_idp(user_id, email_password=email_password)

    assert get.call_count == 1
    assert put.call_count == 0


def test_get_user_workspaces(user_utils, requests_mock):
    user_id = "user1"
    get = requests_mock.get(
        f"{MAS_API_URL}/v3/users/{user_id}/workspaces",
        request_headers={"x-access-token": TOKEN},
        json=[{"id": "masdev"}],
        status_code=200
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
        status_code=404
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
        status_code=500
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
        status_code=200
    )
    put = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json=[{"id": "masdev"}],
        status_code=200
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
        status_code=200
    )
    put = requests_mock.put(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={},
        status_code=200
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
        status_code=200
    )
    put = requests_mock.put(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"error": "internal"},
        status_code=500
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
        "workspaceUrl": "https://api.yourmasdomain.com/workspaces/myworkspace1"
    }
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json=response_json,
        status_code=200
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
        status_code=404
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
        status_code=500
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
        status_code=404
    )
    put = requests_mock.put(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={},
        status_code=200
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
        "workspaceUrl": "https://api.yourmasdomain.com/workspaces/myworkspace1"
    }
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json=get_response_json,
        status_code=200
    )
    put = requests_mock.put(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={},
        status_code=200
    )
    user_utils.set_user_application_permission(user_id, application_id, "USER")
    assert get.call_count == 1
    assert put.call_count == 0
