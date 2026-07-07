# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from unittest.mock import patch, mock_open
from kubernetes.config.config_exception import ConfigException

from mas.devops.ocp import connect


class TestOcpConnect:
    """Test suite for ocp.connect() function."""

    @patch("mas.devops.ocp.config.load_kube_config")
    @patch("mas.devops.ocp.os.makedirs")
    @patch("mas.devops.ocp.os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.ocp.yaml.safe_load")
    @patch("mas.devops.ocp.yaml.dump")
    def test_connect_success(self, mock_yaml_dump, mock_yaml_load, mock_file, mock_exists, mock_makedirs, mock_load_config):
        """Test successful connection to OCP cluster."""
        # Setup - kubeconfig exists with existing content
        mock_exists.return_value = True
        mock_yaml_load.return_value = {"apiVersion": "v1", "kind": "Config", "clusters": [], "users": [], "contexts": [], "current-context": ""}

        # Execute
        result = connect(
            server="https://api.test.example.com:6443",
            token="test-token-123",
            skipVerify=False,
        )

        # Verify
        assert result is True
        mock_yaml_dump.assert_called_once()
        mock_load_config.assert_called_once()
        # Verify the kubeconfig was written
        assert mock_file.call_count >= 2  # Once for read, once for write

    @patch("mas.devops.ocp.config.load_kube_config")
    @patch("mas.devops.ocp.os.makedirs")
    @patch("mas.devops.ocp.os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.ocp.yaml.safe_load")
    @patch("mas.devops.ocp.yaml.dump")
    def test_connect_with_tls_skip(self, mock_yaml_dump, mock_yaml_load, mock_file, mock_exists, mock_makedirs, mock_load_config):
        """Test connection with TLS verification skipped."""
        # Setup - kubeconfig exists
        mock_exists.return_value = True
        mock_yaml_load.return_value = {"apiVersion": "v1", "kind": "Config", "clusters": [], "users": [], "contexts": [], "current-context": ""}

        # Execute
        result = connect(
            server="https://api.test.example.com:6443",
            token="test-token-123",
            skipVerify=True,
        )

        # Verify
        assert result is True
        # Verify yaml.dump was called with correct structure
        call_args = mock_yaml_dump.call_args[0][0]
        assert call_args["clusters"][0]["cluster"]["insecure-skip-tls-verify"] is True

    @patch("mas.devops.ocp.config.load_kube_config")
    @patch("mas.devops.ocp.os.makedirs")
    @patch("mas.devops.ocp.os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.ocp.yaml.safe_load")
    @patch("mas.devops.ocp.yaml.dump")
    def test_connect_config_exception(self, mock_yaml_dump, mock_yaml_load, mock_file, mock_exists, mock_makedirs, mock_load_config):
        """Test connection failure with ConfigException."""
        # Setup - kubeconfig exists
        mock_exists.return_value = True
        mock_yaml_load.return_value = {"apiVersion": "v1", "kind": "Config", "clusters": [], "users": [], "contexts": [], "current-context": ""}

        # Setup mock to raise ConfigException
        mock_load_config.side_effect = ConfigException("Invalid configuration")

        # Execute
        result = connect(
            server="https://api.test.example.com:6443",
            token="test-token-123",
        )

        # Verify
        assert result is False

    @patch("mas.devops.ocp.config.load_kube_config")
    @patch("mas.devops.ocp.os.makedirs")
    @patch("mas.devops.ocp.os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.ocp.yaml.safe_load")
    @patch("mas.devops.ocp.yaml.dump")
    def test_connect_unexpected_exception(self, mock_yaml_dump, mock_yaml_load, mock_file, mock_exists, mock_makedirs, mock_load_config):
        """Test connection failure with unexpected exception."""
        # Setup - kubeconfig exists
        mock_exists.return_value = True
        mock_yaml_load.return_value = {"apiVersion": "v1", "kind": "Config", "clusters": [], "users": [], "contexts": [], "current-context": ""}

        # Setup mock to raise unexpected exception
        mock_load_config.side_effect = RuntimeError("Unexpected error")

        # Execute
        result = connect(
            server="https://api.test.example.com:6443",
            token="test-token-123",
        )

        # Verify
        assert result is False

    @patch("mas.devops.ocp.config.load_kube_config")
    @patch("mas.devops.ocp.os.makedirs")
    @patch("mas.devops.ocp.os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.ocp.yaml.dump")
    def test_connect_creates_new_kubeconfig(self, mock_yaml_dump, mock_file, mock_exists, mock_makedirs, mock_load_config):
        """Test connection creates new kubeconfig when it doesn't exist."""
        # Setup - kubeconfig doesn't exist
        mock_exists.return_value = False

        # Execute
        result = connect(
            server="https://api.test.example.com:6443",
            token="test-token-123",
            skipVerify=False,
        )

        # Verify
        assert result is True
        mock_makedirs.assert_called_once()  # Should create directory
        mock_yaml_dump.assert_called_once()
        mock_load_config.assert_called_once()
