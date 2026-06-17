# *****************************************************************************
# Copyright (c) 2025 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from importlib.machinery import SourceFileLoader
import os
import sys
import pytest
from unittest.mock import Mock, patch
from mas.devops.slack import SlackUtil

# Import functions from the notify-slack script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../bin"))
script_path = os.path.join(
    os.path.dirname(__file__), "../../bin/mas-devops-notify-slack"
)
notify_slack = SourceFileLoader("notify_slack", script_path).load_module()


def testSendMessage():
    response = SlackUtil.postMessageText(
        "#bot-test", "mas-devops postMessageTest() unittest"
    )

    assert "channel" in response.data
    assert response.data["channel"] == "C06453F9KFC"

    assert "ok" in response.data
    assert response.data["ok"] is True

    assert "ts" in response.data


def testBroadcast():
    responses = SlackUtil.postMessageText(
        ["#bot-test", "#bot-test"], "mas-devops postMessageText() broadcast unittest"
    )
    assert len(responses) == 2
    for response in responses:
        assert "channel" in response.data
        assert response.data["channel"] == "C06453F9KFC"

        assert "ok" in response.data
        assert response.data["ok"] is True

        assert "ts" in response.data


# Tests for _getClusterName function
def test_getClusterName_success():
    """Test _getClusterName returns cluster name when env var is set"""
    with patch.dict(os.environ, {"CLUSTER_NAME": "test-cluster"}):
        result = notify_slack._getClusterName()
        assert result == "test-cluster"


def test_getClusterName_missing():
    """Test _getClusterName exits when CLUSTER_NAME is not set"""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(SystemExit) as exc_info:
            notify_slack._getClusterName()
        assert exc_info.value.code == 1


def test_getClusterName_empty():
    """Test _getClusterName exits when CLUSTER_NAME is empty"""
    with patch.dict(os.environ, {"CLUSTER_NAME": ""}):
        with pytest.raises(SystemExit) as exc_info:
            notify_slack._getClusterName()
        assert exc_info.value.code == 1


# Tests for _getToolchainLink function
def test_getToolchainLink_both_set():
    """Test _getToolchainLink returns formatted link when both env vars are set"""
    with patch.dict(
        os.environ,
        {
            "TOOLCHAIN_PIPELINERUN_URL": "https://example.com/pipeline",
            "TOOLCHAIN_TRIGGER_NAME": "test-trigger",
        },
    ):
        result = notify_slack._getToolchainLink()
        assert result == "<https://example.com/pipeline|test-trigger>"


def test_getToolchainLink_url_only():
    """Test _getToolchainLink returns empty string when only URL is set"""
    with patch.dict(
        os.environ,
        {"TOOLCHAIN_PIPELINERUN_URL": "https://example.com/pipeline"},
        clear=True,
    ):
        result = notify_slack._getToolchainLink()
        assert result == ""


def test_getToolchainLink_trigger_only():
    """Test _getToolchainLink returns empty string when only trigger name is set"""
    with patch.dict(os.environ, {"TOOLCHAIN_TRIGGER_NAME": "test-trigger"}, clear=True):
        result = notify_slack._getToolchainLink()
        assert result == ""


def test_getToolchainLink_none_set():
    """Test _getToolchainLink returns empty string when neither env var is set"""
    with patch.dict(os.environ, {}, clear=True):
        result = notify_slack._getToolchainLink()
        assert result == ""


# Tests for notifyProvisionFyre function
@patch.object(SlackUtil, "postMessageBlocks")
def test_notifyProvisionFyre_success(mock_post):
    """Test notifyProvisionFyre with successful provisioning (rc=0)"""
    mock_response = Mock()
    mock_response.data = {"ok": True, "channel": "C123", "ts": "1234567890.123456"}
    mock_post.return_value = mock_response

    with patch.dict(
        os.environ,
        {
            "CLUSTER_NAME": "test-cluster",
            "OCP_CONSOLE_URL": "https://console.example.com",
            "OCP_USERNAME": "admin",
            "OCP_PASSWORD": "password123",  # pragma: allowlist secret
        },
    ):
        result = notify_slack.notifyProvisionFyre(["#test-channel"], 0)
        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert len(call_args[0][1]) == 4  # 4 message blocks


@patch.object(SlackUtil, "postMessageBlocks")
def test_notifyProvisionFyre_success_with_additional_msg(mock_post):
    """Test notifyProvisionFyre with successful provisioning and additional message"""
    mock_response = Mock()
    mock_response.data = {"ok": True, "channel": "C123", "ts": "1234567890.123456"}
    mock_post.return_value = mock_response

    with patch.dict(
        os.environ,
        {
            "CLUSTER_NAME": "test-cluster",
            "OCP_CONSOLE_URL": "https://console.example.com",
            "OCP_USERNAME": "admin",
            "OCP_PASSWORD": "password123",  # pragma: allowlist secret
        },
    ):
        result = notify_slack.notifyProvisionFyre(
            ["#test-channel"], 0, "Additional info"
        )
        assert result is True
        call_args = mock_post.call_args
        assert len(call_args[0][1]) == 5  # 5 message blocks with additional message


@patch.object(SlackUtil, "postMessageBlocks")
def test_notifyProvisionFyre_failure(mock_post):
    """Test notifyProvisionFyre with failed provisioning (rc!=0)"""
    mock_response = Mock()
    mock_response.data = {"ok": True, "channel": "C123", "ts": "1234567890.123456"}
    mock_post.return_value = mock_response

    with patch.dict(os.environ, {"CLUSTER_NAME": "test-cluster"}):
        result = notify_slack.notifyProvisionFyre(["#test-channel"], 1)
        assert result is True
        call_args = mock_post.call_args
        assert len(call_args[0][1]) == 2  # 2 message blocks for failure


@patch.object(SlackUtil, "postMessageBlocks")
def test_notifyProvisionFyre_multiple_channels(mock_post):
    """Test notifyProvisionFyre with multiple channels"""
    mock_response1 = Mock()
    mock_response1.data = {"ok": True, "channel": "C123", "ts": "1234567890.123456"}
    mock_response2 = Mock()
    mock_response2.data = {"ok": True, "channel": "C456", "ts": "1234567890.123457"}
    mock_post.return_value = [mock_response1, mock_response2]

    with patch.dict(os.environ, {"CLUSTER_NAME": "test-cluster"}):
        result = notify_slack.notifyProvisionFyre(["#channel1", "#channel2"], 1)
        assert result is True


def test_notifyProvisionFyre_missing_env_vars():
    """Test notifyProvisionFyre exits when required env vars are missing for success case"""
    with patch.dict(os.environ, {"CLUSTER_NAME": "test-cluster"}, clear=True):
        with pytest.raises(SystemExit) as exc_info:
            notify_slack.notifyProvisionFyre(["#test-channel"], 0)
        assert exc_info.value.code == 1


# Tests for notifyProvisionRoks function
@patch.object(SlackUtil, "postMessageBlocks")
def test_notifyProvisionRoks_success(mock_post):
    """Test notifyProvisionRoks with successful provisioning (rc=0)"""
    mock_response = Mock()
    mock_response.data = {"ok": True, "channel": "C123", "ts": "1234567890.123456"}
    mock_post.return_value = mock_response

    with patch.dict(
        os.environ,
        {
            "CLUSTER_NAME": "test-cluster",
            "OCP_CONSOLE_URL": "https://console.example.com",
        },
    ):
        result = notify_slack.notifyProvisionRoks(["#test-channel"], 0)
        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert len(call_args[0][1]) == 3  # 3 message blocks


@patch.object(SlackUtil, "postMessageBlocks")
def test_notifyProvisionRoks_success_with_additional_msg(mock_post):
    """Test notifyProvisionRoks with successful provisioning and additional message"""
    mock_response = Mock()
    mock_response.data = {"ok": True, "channel": "C123", "ts": "1234567890.123456"}
    mock_post.return_value = mock_response

    with patch.dict(
        os.environ,
        {
            "CLUSTER_NAME": "test-cluster",
            "OCP_CONSOLE_URL": "https://console.example.com",
        },
    ):
        result = notify_slack.notifyProvisionRoks(["#test-channel"], 0, "Extra details")
        assert result is True
        call_args = mock_post.call_args
        assert len(call_args[0][1]) == 4  # 4 message blocks with additional message


@patch.object(SlackUtil, "postMessageBlocks")
def test_notifyProvisionRoks_failure(mock_post):
    """Test notifyProvisionRoks with failed provisioning (rc!=0)"""
    mock_response = Mock()
    mock_response.data = {"ok": True, "channel": "C123", "ts": "1234567890.123456"}
    mock_post.return_value = mock_response

    with patch.dict(os.environ, {"CLUSTER_NAME": "test-cluster"}):
        result = notify_slack.notifyProvisionRoks(["#test-channel"], 1)
        assert result is True
        call_args = mock_post.call_args
        assert len(call_args[0][1]) == 2  # 2 message blocks for failure


def test_notifyProvisionRoks_missing_url():
    """Test notifyProvisionRoks exits when OCP_CONSOLE_URL is missing for success case"""
    with patch.dict(os.environ, {"CLUSTER_NAME": "test-cluster"}, clear=True):
        with pytest.raises(SystemExit) as exc_info:
            notify_slack.notifyProvisionRoks(["#test-channel"], 0)
        assert exc_info.value.code == 1


# Tests for notifyPipelineStart function
@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "createThreadConfigMap")
@patch.object(SlackUtil, "updateThreadConfigMap")
def test_notifyPipelineStart_new_thread(mock_update, mock_create, mock_post, mock_get):
    """Test notifyPipelineStart creates new thread when none exists"""
    # First call returns None, second call returns the created thread info
    thread_info = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
    }
    mock_get.side_effect = [None, thread_info]
    mock_response = Mock()
    mock_response.data = {"ok": True, "channel": "C123", "ts": "1234567890.123456"}
    mock_response.__getitem__ = lambda self, key: (
        mock_response.data[key] if key in ["ts", "channel"] else None
    )
    mock_post.return_value = mock_response

    result = notify_slack.notifyPipelineStart(
        ["#test-channel"], "test-instance", "Install"
    )

    assert result is not None
    assert result == thread_info
    mock_post.assert_called_once()
    mock_create.assert_called_once()
    mock_update.assert_called_once()


@patch.object(SlackUtil, "getThreadConfigMap")
def test_notifyPipelineStart_existing_thread(mock_get):
    """Test notifyPipelineStart returns existing thread info"""
    existing_thread = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
    }
    mock_get.return_value = existing_thread

    result = notify_slack.notifyPipelineStart(
        ["#test-channel"], "test-instance", "Install"
    )

    assert result == existing_thread


# These tests are removed because None/empty instanceId is now valid for update pipeline
# See new tests: test_notifyPipelineStart_update_pipeline_no_instance_id and
# test_notifyPipelineStart_update_pipeline_empty_instance_id


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "createThreadConfigMap")
@patch.object(SlackUtil, "updateThreadConfigMap")
def test_notifyPipelineStart_multiple_channels(
    mock_update, mock_create, mock_post, mock_get
):
    """Test notifyPipelineStart with multiple channels"""
    # First call returns None, second call returns the created thread info
    thread_info = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_1": "C456",
        "threadId_1": "1234567890.123457",
        "channel_count": "2",
    }
    mock_get.side_effect = [None, thread_info]
    mock_response1 = Mock()
    mock_response1.data = {"ok": True, "channel": "C123", "ts": "1234567890.123456"}
    mock_response1.__getitem__ = lambda self, key: (
        mock_response1.data[key] if key in ["ts", "channel"] else None
    )
    mock_response2 = Mock()
    mock_response2.data = {"ok": True, "channel": "C456", "ts": "1234567890.123457"}
    mock_response2.__getitem__ = lambda self, key: (
        mock_response2.data[key] if key in ["ts", "channel"] else None
    )
    mock_post.return_value = [mock_response1, mock_response2]

    result = notify_slack.notifyPipelineStart(
        ["#channel1", "#channel2"], "test-instance", "Install"
    )

    assert result is not None
    # Verify that channel_count is set to 2
    update_call_args = mock_update.call_args[0][2]
    assert update_call_args["channel_count"] == "2"


# Tests for notifyAnsibleStart function
@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "updateThreadConfigMap")
def test_notifyAnsibleStart_success(mock_update, mock_post, mock_get):
    """Test notifyAnsibleStart sends task start message"""
    mock_get.return_value = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
    }
    mock_response = Mock()
    mock_response.data = {"ok": True, "ts": "1234567890.123457"}
    mock_post.return_value = mock_response

    result = notify_slack.notifyAnsibleStart(
        ["#test-channel"], "install-mas", "test-instance", "Install"
    )

    assert result is True
    mock_post.assert_called_once()
    mock_update.assert_called_once()


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "updateThreadConfigMap")
def test_notifyAnsibleStart_creates_thread_if_missing(mock_update, mock_post, mock_get):
    """Test notifyAnsibleStart creates pipeline thread if it doesn't exist"""
    # First call returns None (no thread), second call returns None (checking again in notifyPipelineStart),
    # third call returns thread info (after creation), fourth call returns thread info (for ansible start)
    thread_info = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
    }
    mock_get.side_effect = [None, None, thread_info, thread_info]

    # Mock for notifyPipelineStart's postMessageBlocks call
    mock_pipeline_response = Mock()
    mock_pipeline_response.data = {
        "ok": True,
        "channel": "C123",
        "ts": "1234567890.123456",
    }
    mock_pipeline_response.__getitem__ = lambda self, key: (
        mock_pipeline_response.data[key] if key in ["ts", "channel"] else None
    )

    # Mock for notifyAnsibleStart's postMessageBlocks call
    mock_task_response = Mock()
    mock_task_response.data = {"ok": True, "ts": "1234567890.123457"}

    mock_post.side_effect = [mock_pipeline_response, mock_task_response]

    with patch.object(SlackUtil, "createThreadConfigMap"):
        result = notify_slack.notifyAnsibleStart(
            ["#test-channel"], "install-mas", "test-instance", "Install"
        )

    assert result is True
    assert mock_post.call_count == 2  # Once for pipeline start, once for task start


# This test is removed because None instanceId is now valid for update pipeline
# See new test: test_notifyAnsibleStart_update_pipeline_no_instance_id


@patch.object(SlackUtil, "getThreadConfigMap")
def test_notifyAnsibleStart_no_channels(mock_get):
    """Test notifyAnsibleStart returns False when no channels found"""
    mock_get.return_value = {"instanceId": "test-instance", "channel_count": "0"}

    result = notify_slack.notifyAnsibleStart(
        ["#test-channel"], "task-name", "test-instance", "Install"
    )

    assert result is False


# Tests for notifyAnsibleComplete function
@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "updateMessageBlocks")
def test_notifyAnsibleComplete_success(mock_update, mock_get):
    """Test notifyAnsibleComplete with successful task (rc=0)"""
    mock_get.return_value = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "task_install-mas_0": "1234567890.123457",
        "channel_count": "1",
    }
    mock_response = Mock()
    mock_response.data = {"ok": True}
    mock_update.return_value = mock_response

    result = notify_slack.notifyAnsibleComplete(
        ["#test-channel"], 0, "install-mas", "test-instance", "Install"
    )

    assert result is True
    mock_update.assert_called_once()


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "updateMessageBlocks")
def test_notifyAnsibleComplete_failure(mock_update, mock_get):
    """Test notifyAnsibleComplete with failed task (rc!=0)"""
    mock_get.return_value = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "task_install-mas_0": "1234567890.123457",
        "channel_count": "1",
    }
    mock_response = Mock()
    mock_response.data = {"ok": True}
    mock_update.return_value = mock_response

    result = notify_slack.notifyAnsibleComplete(
        ["#test-channel"], 1, "install-mas", "test-instance", "Install"
    )

    assert result is True
    # Verify failure message includes return code
    call_args = mock_update.call_args[0][2]
    assert (
        len(call_args) == 2
    )  # Should have 2 blocks for failure (status + error details)


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
def test_notifyAnsibleComplete_no_start_message(mock_post, mock_get):
    """Test notifyAnsibleComplete posts new message when start message not found"""
    mock_get.return_value = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
    }
    mock_response = Mock()
    mock_response.data = {"ok": True}
    mock_post.return_value = mock_response

    result = notify_slack.notifyAnsibleComplete(
        ["#test-channel"], 0, "install-mas", "test-instance", "Install"
    )

    assert result is True
    mock_post.assert_called_once()


# This test is removed because None instanceId is now valid for update pipeline
# See new test: test_notifyAnsibleComplete_update_pipeline_no_instance_id


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
def test_notifyAnsibleComplete_creates_thread_if_missing(mock_post, mock_get):
    """Test notifyAnsibleComplete creates pipeline thread if it doesn't exist"""
    # First call returns None (no thread), second call returns None (checking again in notifyPipelineStart),
    # third call returns thread info (after creation), fourth call returns thread info (for ansible complete)
    thread_info = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
    }
    mock_get.side_effect = [None, None, thread_info, thread_info]

    # Mock for notifyPipelineStart's postMessageBlocks call
    mock_pipeline_response = Mock()
    mock_pipeline_response.data = {
        "ok": True,
        "channel": "C123",
        "ts": "1234567890.123456",
    }
    mock_pipeline_response.__getitem__ = lambda self, key: (
        mock_pipeline_response.data[key] if key in ["ts", "channel"] else None
    )

    # Mock for notifyAnsibleComplete's postMessageBlocks call
    mock_complete_response = Mock()
    mock_complete_response.data = {"ok": True}

    mock_post.side_effect = [mock_pipeline_response, mock_complete_response]

    with patch.object(SlackUtil, "createThreadConfigMap"), patch.object(
        SlackUtil, "updateThreadConfigMap"
    ):
        result = notify_slack.notifyAnsibleComplete(
            ["#test-channel"], 0, "install-mas", "test-instance", "Install"
        )

    assert result is True
    assert mock_post.call_count == 2  # Once for pipeline start, once for task complete


# Tests for notifyPipelineComplete function
@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "deleteThreadConfigMap")
def test_notifyPipelineComplete_success(mock_delete, mock_post, mock_get):
    """Test notifyPipelineComplete with successful pipeline (rc=0)"""
    mock_get.return_value = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
    }
    mock_response = Mock()
    mock_response.data = {"ok": True}
    mock_post.return_value = mock_response

    result = notify_slack.notifyPipelineComplete(
        ["#test-channel"], 0, "test-instance", "Install"
    )

    assert result is True
    mock_post.assert_called_once()
    mock_delete.assert_called_once()


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "deleteThreadConfigMap")
def test_notifyPipelineComplete_failure(mock_delete, mock_post, mock_get):
    """Test notifyPipelineComplete with failed pipeline (rc!=0)"""
    mock_get.return_value = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
    }
    mock_response = Mock()
    mock_response.data = {"ok": True}
    mock_post.return_value = mock_response

    result = notify_slack.notifyPipelineComplete(
        ["#test-channel"], 1, "test-instance", "Install"
    )

    assert result is True
    mock_delete.assert_called_once()


@patch.object(SlackUtil, "getThreadConfigMap")
def test_notifyPipelineComplete_no_thread_info(mock_get):
    """Test notifyPipelineComplete returns False when no thread info found"""
    mock_get.return_value = None

    result = notify_slack.notifyPipelineComplete(
        ["#test-channel"], 0, "test-instance", "Install"
    )

    assert result is False


# This test is removed because None instanceId is now valid for update pipeline
# See new test: test_notifyPipelineComplete_update_pipeline_no_instance_id


@patch.object(SlackUtil, "getThreadConfigMap")
def test_notifyPipelineComplete_no_channels(mock_get):
    """Test notifyPipelineComplete returns False when no channels found"""
    mock_get.return_value = {"instanceId": "test-instance", "channel_count": "0"}

    result = notify_slack.notifyPipelineComplete(
        ["#test-channel"], 0, "test-instance", "Install"
    )

    assert result is False


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "deleteThreadConfigMap")
def test_notifyPipelineComplete_multiple_channels(mock_delete, mock_post, mock_get):
    """Test notifyPipelineComplete with multiple channels"""
    mock_get.return_value = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_1": "C456",
        "threadId_1": "1234567890.123457",
        "channel_count": "2",
    }
    mock_response = Mock()
    mock_response.data = {"ok": True}
    mock_post.return_value = mock_response

    result = notify_slack.notifyPipelineComplete(
        ["#channel1", "#channel2"], 0, "test-instance", "Install"
    )

    assert result is True
    assert mock_post.call_count == 2
    mock_delete.assert_called_once()


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "deleteThreadConfigMap")
def test_notifyPipelineComplete_with_duration(mock_delete, mock_post, mock_get):
    """Test notifyPipelineComplete includes duration when startTime is available"""
    mock_get.return_value = {
        "instanceId": "test-instance",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
        "startTime": "2026-03-10T18:00:00Z",
    }
    mock_response = Mock()
    mock_response.data = {"ok": True}
    mock_post.return_value = mock_response

    result = notify_slack.notifyPipelineComplete(
        ["#test-channel"], 0, "test-instance", "Install"
    )

    assert result is True
    # Verify that postMessageBlocks was called
    mock_post.assert_called_once()
    mock_delete.assert_called_once()


# Tests for update pipeline (no instance ID) scenarios
@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "createThreadConfigMap")
@patch.object(SlackUtil, "updateThreadConfigMap")
def test_notifyPipelineStart_update_pipeline_no_instance_id(
    mock_update, mock_create, mock_post, mock_get
):
    """Test notifyPipelineStart for update pipeline with no instance ID"""
    # First call returns None, second call returns the created thread info
    thread_info = {
        "instanceId": "",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
    }
    mock_get.side_effect = [None, thread_info]
    mock_response = Mock()
    mock_response.data = {"ok": True, "channel": "C123", "ts": "1234567890.123456"}
    mock_response.__getitem__ = lambda self, key: (
        mock_response.data[key] if key in ["ts", "channel"] else None
    )
    mock_post.return_value = mock_response

    result = notify_slack.notifyPipelineStart(["#test-channel"], None, "Update")

    assert result is not None
    assert result == thread_info
    mock_post.assert_called_once()
    mock_create.assert_called_once()
    # Verify that createThreadConfigMap was called with None for instanceId
    assert mock_create.call_args[0][1] is None
    mock_update.assert_called_once()


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "updateThreadConfigMap")
def test_notifyAnsibleStart_update_pipeline_no_instance_id(
    mock_update, mock_post, mock_get
):
    """Test notifyAnsibleStart for update pipeline with no instance ID"""
    mock_get.return_value = {
        "instanceId": "",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
    }
    mock_response = Mock()
    mock_response.data = {"ok": True, "ts": "1234567890.123457"}
    mock_post.return_value = mock_response

    result = notify_slack.notifyAnsibleStart(
        ["#test-channel"], "update-catalog", None, "Update"
    )

    assert result is True
    mock_post.assert_called_once()
    mock_update.assert_called_once()
    # Verify that updateThreadConfigMap was called with None for instanceId
    assert mock_update.call_args[0][1] is None


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "updateMessageBlocks")
def test_notifyAnsibleComplete_update_pipeline_no_instance_id(mock_update, mock_get):
    """Test notifyAnsibleComplete for update pipeline with no instance ID"""
    mock_get.return_value = {
        "instanceId": "",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "task_update-catalog_0": "1234567890.123457",
        "channel_count": "1",
    }
    mock_response = Mock()
    mock_response.data = {"ok": True}
    mock_update.return_value = mock_response

    result = notify_slack.notifyAnsibleComplete(
        ["#test-channel"], 0, "update-catalog", None, "Update"
    )

    assert result is True
    mock_update.assert_called_once()


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "deleteThreadConfigMap")
def test_notifyPipelineComplete_update_pipeline_no_instance_id(
    mock_delete, mock_post, mock_get
):
    """Test notifyPipelineComplete for update pipeline with no instance ID"""
    mock_get.return_value = {
        "instanceId": "",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
    }
    mock_response = Mock()
    mock_response.data = {"ok": True}
    mock_post.return_value = mock_response

    result = notify_slack.notifyPipelineComplete(["#test-channel"], 0, None, "Update")

    assert result is True
    mock_post.assert_called_once()
    mock_delete.assert_called_once()
    # Verify that deleteThreadConfigMap was called with None for instanceId
    assert mock_delete.call_args[0][1] is None


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "deleteThreadConfigMap")
def test_notifyPipelineComplete_update_pipeline_empty_instance_id(
    mock_delete, mock_post, mock_get
):
    """Test notifyPipelineComplete for update pipeline with empty string instance ID"""
    mock_get.return_value = {
        "instanceId": "",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_count": "1",
    }
    mock_response = Mock()
    mock_response.data = {"ok": True}
    mock_post.return_value = mock_response

    result = notify_slack.notifyPipelineComplete(["#test-channel"], 0, "", "Update")

    assert result is True
    mock_post.assert_called_once()
    mock_delete.assert_called_once()
    # Verify that deleteThreadConfigMap was called with empty string for instanceId
    assert mock_delete.call_args[0][1] == ""


@patch.object(SlackUtil, "getThreadConfigMap")
@patch.object(SlackUtil, "postMessageBlocks")
@patch.object(SlackUtil, "createThreadConfigMap")
@patch.object(SlackUtil, "updateThreadConfigMap")
def test_notifyPipelineStart_update_pipeline_multiple_channels(
    mock_update, mock_create, mock_post, mock_get
):
    """Test notifyPipelineStart for update pipeline with multiple channels and no instance ID"""
    # First call returns None, second call returns the created thread info
    thread_info = {
        "instanceId": "",
        "channel_0": "C123",
        "threadId_0": "1234567890.123456",
        "channel_1": "C456",
        "threadId_1": "1234567890.123457",
        "channel_count": "2",
    }
    mock_get.side_effect = [None, thread_info]
    mock_response1 = Mock()
    mock_response1.data = {"ok": True, "channel": "C123", "ts": "1234567890.123456"}
    mock_response1.__getitem__ = lambda self, key: (
        mock_response1.data[key] if key in ["ts", "channel"] else None
    )
    mock_response2 = Mock()
    mock_response2.data = {"ok": True, "channel": "C456", "ts": "1234567890.123457"}
    mock_response2.__getitem__ = lambda self, key: (
        mock_response2.data[key] if key in ["ts", "channel"] else None
    )
    mock_post.return_value = [mock_response1, mock_response2]

    result = notify_slack.notifyPipelineStart(
        ["#channel1", "#channel2"], None, "Update"
    )

    assert result is not None
    # Verify that channel_count is set to 2
    update_call_args = mock_update.call_args[0][2]
    assert update_call_args["channel_count"] == "2"
    # Verify namespace is mas-pipelines (not mas-None-pipelines)
    assert mock_create.call_args[0][0] == "mas-pipelines"
