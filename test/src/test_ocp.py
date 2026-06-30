# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from unittest.mock import ANY
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import yaml

from mas.devops import ocp


def test_is_cluster_in_range():
    assert ocp.isClusterVersionInRange("4.1.6", None) is False
    assert ocp.isClusterVersionInRange("4.1.6", []) is False
    assert ocp.isClusterVersionInRange("4.1.6", ["4.16", "4.17", "4.18"]) is False
    assert ocp.isClusterVersionInRange("4.12.6", ["4.16", "4.17", "4.18"]) is False
    assert ocp.isClusterVersionInRange("4.15.6", ["4.16", "4.17", "4.18"]) is False
    assert ocp.isClusterVersionInRange("4.16.0", ["4.16", "4.17", "4.18"]) is True
    assert ocp.isClusterVersionInRange("4.18.1", ["4.16", "4.17", "4.18"]) is True
    assert ocp.isClusterVersionInRange("5.0.0", ["4.16", "4.17", "4.18"]) is False


def test_execInPod_success():
    with patch("kubernetes.client.CoreV1Api") as mock_CoreV1Api, patch("mas.devops.ocp.stream") as mock_stream:
        mock_core_v1_api = mock_CoreV1Api.return_value

        mock_req = mock_stream.return_value
        mock_req.run_forever.return_value = None
        mock_req.read_stdout.return_value = "mock_stdout"
        mock_req.read_stderr.return_value = "mock_stderr"
        mock_req.read_channel.return_value = yaml.dump({"status": "Success"})

        o = ocp.execInPod(mock_core_v1_api, "pod_name", "namespace", ["command"])
        assert o == "mock_stdout"


def test_execInPod_failure():
    with patch("kubernetes.client.CoreV1Api") as mock_CoreV1Api, patch("mas.devops.ocp.stream") as mock_stream:
        mock_core_v1_api = mock_CoreV1Api.return_value

        mock_req = mock_stream.return_value
        mock_req.run_forever.return_value = None
        mock_req.read_stdout.return_value = "mock_stdout"
        mock_req.read_stderr.return_value = "mock_stderr"
        mock_req.read_channel.return_value = yaml.dump({"status": "Failure"})

        with pytest.raises(
            Exception,
            match=r"Failed to execute \['command'\] on pod_name in namespace namespace: None. stdout: mock_stdout, stderr: mock_stderr",
        ):
            ocp.execInPod(mock_core_v1_api, "pod_name", "namespace", ["command"])


def test_applyResource_creates_namespaced_resource():
    mock_dyn_client = MagicMock()
    mock_resource_api = MagicMock()
    mock_dyn_client.resources.get.return_value = mock_resource_api
    mock_api_exception = MagicMock()
    mock_api_exception.status = 404
    mock_api_exception.reason = "Not Found"
    mock_resource_api.get.side_effect = ocp.NotFoundError(mock_api_exception)

    body = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "test-secret"},
    }

    ocp.applyResource(
        dynClient=mock_dyn_client,
        apiVersion="v1",
        kind="Secret",
        body=body,
        namespace="test-namespace",
    )

    mock_resource_api.get.assert_called_once_with(name="test-secret", namespace="test-namespace")
    mock_resource_api.create.assert_called_once_with(body=body, namespace="test-namespace")
    mock_resource_api.patch.assert_not_called()


def test_applyResource_patches_namespaced_resource():
    mock_dyn_client = MagicMock()
    mock_resource_api = MagicMock()
    mock_dyn_client.resources.get.return_value = mock_resource_api

    body = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "test-secret"},
    }

    ocp.applyResource(
        dynClient=mock_dyn_client,
        apiVersion="v1",
        kind="Secret",
        body=body,
        namespace="test-namespace",
    )

    mock_resource_api.get.assert_called_once_with(name="test-secret", namespace="test-namespace")
    mock_resource_api.patch.assert_called_once_with(
        body=body,
        name="test-secret",
        namespace="test-namespace",
        content_type="application/merge-patch+json",
    )
    mock_resource_api.create.assert_not_called()


def test_applyResource_creates_cluster_scoped_resource():
    mock_dyn_client = MagicMock()
    mock_resource_api = MagicMock()
    mock_dyn_client.resources.get.return_value = mock_resource_api
    mock_api_exception = MagicMock()
    mock_api_exception.status = 404
    mock_api_exception.reason = "Not Found"
    mock_resource_api.get.side_effect = ocp.NotFoundError(mock_api_exception)

    body = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRoleBinding",
        "metadata": {"name": "test-binding"},
    }

    ocp.applyResource(
        dynClient=mock_dyn_client,
        apiVersion="rbac.authorization.k8s.io/v1",
        kind="ClusterRoleBinding",
        body=body,
    )

    mock_resource_api.get.assert_called_once_with(name="test-binding")
    mock_resource_api.create.assert_called_once_with(body=body)
    mock_resource_api.patch.assert_not_called()


def test_applyResource_patches_cluster_scoped_resource():
    mock_dyn_client = MagicMock()
    mock_resource_api = MagicMock()
    mock_dyn_client.resources.get.return_value = mock_resource_api

    body = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRoleBinding",
        "metadata": {"name": "test-binding"},
    }

    ocp.applyResource(
        dynClient=mock_dyn_client,
        apiVersion="rbac.authorization.k8s.io/v1",
        kind="ClusterRoleBinding",
        body=body,
    )

    mock_resource_api.get.assert_called_once_with(name="test-binding")
    mock_resource_api.patch.assert_called_once_with(
        body=body,
        name="test-binding",
        content_type="application/merge-patch+json",
    )
    mock_resource_api.create.assert_not_called()


def test_apply_resource_uses_applyResource():
    resource_yaml = """
apiVersion: v1
kind: Secret
metadata:
  name: test-secret
"""

    with patch("mas.devops.ocp.applyResource") as mock_apply_resource:
        ocp.apply_resource(
            dynClient=MagicMock(),
            resource_yaml=resource_yaml,
            namespace="test-namespace",
        )

    mock_apply_resource.assert_called_once_with(
        dynClient=ANY,
        apiVersion="v1",
        kind="Secret",
        body={
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "test-secret"},
        },
        namespace="test-namespace",
    )
