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
    requests_mock.post(f"{MAS_ADMIN_URL}/logininitial", json=dict(token=TOKEN))
    yield user_utils


def mock_get_user(requests_mock, user_id, json, status_code):
    return requests_mock.get(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json=json,
        status_code=status_code
    )


def mock_get_user_200(requests_mock, user_id):
    return mock_get_user(
        requests_mock, user_id, {"id": user_id, "displayName": user_id}, 200
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
    assert user_utils.get_user(user_id) == {"id": user_id, "displayName": user_id}
    assert get.call_count == 1


def test_mas_superuser_credentials():
    pass
    # TODO this and tests for other properties


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

    assert user_utils.get_or_create_user({"id": user_id}) == {"id": user_id, "displayName": user_id}
    assert get.call_count == 1
    assert post.call_count == 0


def test_get_or_create_user_notfound(user_utils, requests_mock):
    user_id = "user1"
    get = mock_get_user_404(requests_mock, user_id)

    post = requests_mock.post(
        f"{MAS_API_URL}/v3/users",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id, "displayName": user_id},
        status_code=201
    )

    assert user_utils.get_or_create_user({"id": user_id}) == {"id": user_id, "displayName": user_id}
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


def test_update_user(user_utils, requests_mock):
    user_id = "user1"
    put = requests_mock.put(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=200
    )
    user_utils.update_user({"id": user_id})
    assert put.call_count == 1


def test_update_user_error(user_utils, requests_mock):
    user_id = "user1"
    put = requests_mock.put(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"error": "nofound"},
        status_code=404
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
        status_code=200
    )
    user_utils.update_user_display_name(user_id, "display_name")
    assert patche.call_count == 1


def test_update_user_display_name_error(user_utils, requests_mock):
    user_id = "user1"
    patche = requests_mock.patch(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"error": "notfound"},
        status_code=404
    )
    with pytest.raises(Exception):
        user_utils.update_user_display_name(user_id, "display_name")
    assert patche.call_count == 1


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


def test_resync_users(user_utils, requests_mock):
    user_ids = ["user1", "user2"]

    gets = []
    patches = []
    for user_id in user_ids:
        gets.append(mock_get_user_200(requests_mock, user_id))

        patches.append(
            requests_mock.patch(
                f"{MAS_API_URL}/v3/users/{user_id}",
                request_headers={"x-access-token": TOKEN},
                json={"id": user_id},
                status_code=200
            )
        )

    user_utils.resync_users(user_ids)

    for get in gets:
        assert get.call_count == 1

    for patche in patches:
        assert patche.call_count == 1


def test_check_user_sync(user_utils, requests_mock):
    user_id = "user1"
    application_id = "manage"

    # transitions from PENDING -> SUCCESS on the third call
    attempts = 0

    def json_callback(request, context):
        nonlocal attempts
        if attempts >= 2:
            state = "SUCCESS"
        else:
            state = "PENDING"
        attempts = attempts + 1
        return {
            "id": user_id,
            "applications": {
                "other": {
                    "sync": {
                        "state": "ERROR"
                    }
                },
                application_id: {
                    "sync": {
                        "state": state
                    }
                }
            }
        }

    get = mock_get_user(
        requests_mock,
        user_id,
        json_callback,
        200
    )

    user_utils.check_user_sync(user_id, application_id, timeout_secs=8, retry_interval_secs=0)
    assert get.call_count == 3


def test_check_user_sync_timeout(user_utils, requests_mock):
    user_id = "user1"
    application_id = "manage"

    get = mock_get_user(
        requests_mock,
        user_id,
        {
            "id": user_id,
            "applications": {
                "other": {
                    "sync": {
                        "state": "ERROR"
                    }
                },
                application_id: {
                    "sync": {
                        "state": "PENDING"
                    }
                }
            }
        },
        200
    )
    with pytest.raises(Exception) as excinfo:
        user_utils.check_user_sync(user_id, application_id, timeout_secs=0.3, retry_interval_secs=0.05)
    assert str(excinfo.value) == f"User {user_id} sync failed to complete for app within {0.3} seconds"
    assert get.call_count > 1


def test_check_user_sync_appstate_notfound(user_utils, requests_mock):
    user_id = "user1"
    application_id = "manage"

    # first call (made bvy check_user_sync) returns user record with missing sync status for app
    # subsequent calls will include sync status and so should succeed
    # a single resync should have been triggered
    attempts = 0

    def json_callback(request, context):
        nonlocal attempts
        if attempts >= 1:
            ret = {
                "id": user_id,
                "displayName": user_id,
                "applications": {
                    "other": {
                        "sync": {
                            "state": "ERROR"
                        }
                    },
                    application_id: {
                        "sync": {
                            "state": "SUCCESS"
                        }
                    }
                }
            }
        else:
            ret = {
                "id": user_id,
                "displayName": user_id,
                "applications": {
                    "other": {
                        "sync": {
                            "state": "ERROR"
                        }
                    },
                }
            }
        attempts = attempts + 1
        return ret

    patche = requests_mock.patch(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=200
    )

    get = mock_get_user(
        requests_mock,
        user_id,
        json_callback,
        200
    )

    user_utils.check_user_sync(user_id, application_id, timeout_secs=8, retry_interval_secs=0)
    assert get.call_count == 3

    # a single resync should have been triggered
    assert patche.call_count == 1


def test_check_user_sync_appstate_transient_error(user_utils, requests_mock):
    user_id = "user1"
    application_id = "manage"

    # first call (made bvy check_user_sync) returns user record with sync state error
    # subsequent calls will have successful sync state and so should succeed
    # a single resync should have been triggered
    attempts = 0

    def json_callback(request, context):
        nonlocal attempts
        if attempts >= 1:
            ret = {
                "id": user_id,
                "displayName": user_id,
                "applications": {
                    application_id: {
                        "sync": {
                            "state": "SUCCESS"
                        }
                    }
                }
            }
        else:
            ret = {
                "id": user_id,
                "displayName": user_id,
                "applications": {
                    application_id: {
                        "sync": {
                            "state": "ERROR"
                        }
                    }
                }
            }
        attempts = attempts + 1
        return ret

    patche = requests_mock.patch(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=200
    )

    get = mock_get_user(
        requests_mock,
        user_id,
        json_callback,
        200
    )

    user_utils.check_user_sync(user_id, application_id, timeout_secs=8, retry_interval_secs=0)
    assert get.call_count == 3

    # a single resync should have been triggered
    assert patche.call_count == 1


def test_check_user_sync_appstate_persistent_error(user_utils, requests_mock):
    user_id = "user1"
    application_id = "manage"

    patche = requests_mock.patch(
        f"{MAS_API_URL}/v3/users/{user_id}",
        request_headers={"x-access-token": TOKEN},
        json={"id": user_id},
        status_code=200
    )

    get = mock_get_user(
        requests_mock,
        user_id,
        {
            "id": user_id,
            "displayName": user_id,
            "applications": {
                application_id: {
                    "sync": {
                        "state": "ERROR"
                    }
                }
            }
        },
        200
    )

    with pytest.raises(Exception) as excinfo:
        user_utils.check_user_sync(user_id, application_id, timeout_secs=0.3, retry_interval_secs=0.05)
    assert str(excinfo.value) == f"User {user_id} sync failed to complete for app within {0.3} seconds"
    assert get.call_count > 1

    # an "update_user_display_name" should have been triggered for every 2 get calls (1 call by check_user_sync, 1 by resync)
    assert patche.call_count == get.call_count / 2


def test_create_or_get_manage_api_key_for_user(user_utils, requests_mock):
    pass
    # TODO


def test_get_manage_api_key_for_user(user_utils, requests_mock):
    pass
    # TODO


def test_delete_manage_api_key(user_utils, requests_mock):
    pass
    # TODO


def test_get_manage_group_id(user_utils, requests_mock):
    pass
    # TODO


def test_is_user_in_manage_group(user_utils, requests_mock):
    pass
    # TODO


def test_add_user_to_manage_group(user_utils, requests_mock):
    pass
    # TODO


def test_get_mas_applications_in_workspace(user_utils, requests_mock):
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications",
        request_headers={"x-access-token": TOKEN},
        json=[{"id": "manage"}],
        status_code=200
    )
    assert user_utils.get_mas_applications_in_workspace() == [{"id": "manage"}]
    assert get.call_count == 1


def test_get_mas_applications_in_workspace_error(user_utils, requests_mock):
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications",
        request_headers={"x-access-token": TOKEN},
        json={"error": "internal"},
        status_code=500
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
        status_code=200
    )
    assert user_utils.get_mas_application_availability(application_id) == {"id": "manage"}
    assert get.call_count == 1


def test_get_mas_application_availability_error(user_utils, requests_mock):
    application_id = "manage"
    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}",
        request_headers={"x-access-token": TOKEN},
        json={"error": "internal"},
        status_code=500
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
        nonlocal return_values
        ret = return_values[attempt]
        attempt = attempt + 1
        return ret

    get = requests_mock.get(
        f"{MAS_API_URL}/workspaces/{MAS_WORKSPACE_ID}/applications/{application_id}",
        request_headers={"x-access-token": TOKEN},
        json=json_callback,
        status_code=200
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
        status_code=200
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
            "user3@example.com": "secondary     ,bill,  bibb"
        }
    )

    expected_initial_users = {
        "users": {
            "primary": [
                {
                    "email": "user1@example.com",
                    "given_name": "joe",
                    "family_name": "bloggs"
                },
                {
                    "email": "user2@example.com",
                    "given_name": "ben",
                    "family_name": "bob"
                }
            ],
            "secondary": [
                {
                    "email": "user3@example.com",
                    "given_name": "bill",
                    "family_name": "bibb"
                }
            ]
        }
    }

    assert actual_initial_users == expected_initial_users

    with pytest.raises(Exception) as excinfo:
        user_utils.parse_initial_users_from_aws_secret_json({
            "user1@example.com": "primary"
        })
    assert "Wrong number of CSV values for user1@example.com (expected 3 but got 1)" == str(excinfo.value)

    with pytest.raises(Exception) as excinfo:
        user_utils.parse_initial_users_from_aws_secret_json({
            "user1@example.com": "unknown,x,y"
        })
    assert "Unknown user type for user1@example.com: unknown" == str(excinfo.value)


def test_create_initial_user_for_saas(user_utils, requests_mock):
    pass


def test_create_initial_users_for_saas(user_utils, requests_mock):
    pass
