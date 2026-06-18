# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from unittest.mock import patch, MagicMock
from kubernetes.config.config_exception import ConfigException

from mas.devops.ocp import connect


class TestOcpConnect:
    """Test suite for ocp.connect() function."""

    @patch("mas.devops.ocp.config.load_kube_config")
    @patch("mas.devops.ocp.os.unlink")
    @patch("mas.devops.ocp.tempfile.NamedTemporaryFile")
    @patch("mas.devops.ocp.yaml.dump")
    def test_connect_success(self, mock_yaml_dump, mock_tempfile, mock_unlink, mock_load_config):
        """Test successful connection to OCP cluster."""
        # Setup mock temporary file
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.kubeconfig"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        # Execute
        result = connect(
            server="https://api.test.example.com:6443",
            token="test-token-123",
            skipVerify=False,
        )

        # Verify
        assert result is True
        mock_yaml_dump.assert_called_once()
        mock_load_config.assert_called_once_with(config_file="/tmp/test.kubeconfig")
        mock_unlink.assert_called_once_with("/tmp/test.kubeconfig")

    @patch("mas.devops.ocp.config.load_kube_config")
    @patch("mas.devops.ocp.os.unlink")
    @patch("mas.devops.ocp.tempfile.NamedTemporaryFile")
    @patch("mas.devops.ocp.yaml.dump")
    def test_connect_with_tls_skip(self, mock_yaml_dump, mock_tempfile, mock_unlink, mock_load_config):
        """Test connection with TLS verification skipped."""
        # Setup mock temporary file
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.kubeconfig"
        mock_tempfile.return_value.__enter__.return_value = mock_file

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
    @patch("mas.devops.ocp.os.unlink")
    @patch("mas.devops.ocp.tempfile.NamedTemporaryFile")
    @patch("mas.devops.ocp.yaml.dump")
    def test_connect_config_exception(self, mock_yaml_dump, mock_tempfile, mock_unlink, mock_load_config):
        """Test connection failure with ConfigException."""
        # Setup mock temporary file
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.kubeconfig"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        # Setup mock to raise ConfigException
        mock_load_config.side_effect = ConfigException("Invalid configuration")

        # Execute
        result = connect(
            server="https://api.test.example.com:6443",
            token="test-token-123",
        )

        # Verify
        assert result is False
        mock_unlink.assert_not_called()  # Should not clean up on error

    @patch("mas.devops.ocp.config.load_kube_config")
    @patch("mas.devops.ocp.os.unlink")
    @patch("mas.devops.ocp.tempfile.NamedTemporaryFile")
    @patch("mas.devops.ocp.yaml.dump")
    def test_connect_unexpected_exception(self, mock_yaml_dump, mock_tempfile, mock_unlink, mock_load_config):
        """Test connection failure with unexpected exception."""
        # Setup mock temporary file
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.kubeconfig"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        # Setup mock to raise unexpected exception
        mock_load_config.side_effect = RuntimeError("Unexpected error")

        # Execute
        result = connect(
            server="https://api.test.example.com:6443",
            token="test-token-123",
        )

        # Verify
        assert result is False
        mock_unlink.assert_not_called()  # Should not clean up on error
