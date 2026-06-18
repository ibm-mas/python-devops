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
from unittest.mock import patch, mock_open, MagicMock
import yaml
from openshift.dynamic.exceptions import ApiException

from mas.devops.tekton import updateTektonDefinitions


class TestUpdateTektonDefinitions:
    """Test suite for tekton.updateTektonDefinitions() function."""

    @patch("mas.devops.tekton.path.isfile")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.tekton.yaml.safe_load_all")
    def test_update_tekton_definitions_success(self, mock_yaml_load, mock_file, mock_isfile):
        """Test successful application of Tekton resources."""
        # Setup
        mock_isfile.return_value = True
        mock_yaml_load.return_value = [
            {
                "apiVersion": "tekton.dev/v1beta1",
                "kind": "Task",
                "metadata": {"name": "test-task"},
                "spec": {},
            },
            {
                "apiVersion": "tekton.dev/v1beta1",
                "kind": "Pipeline",
                "metadata": {"name": "test-pipeline"},
                "spec": {},
            },
        ]

        mock_dyn_client = MagicMock()
        mock_resource_api = MagicMock()
        mock_dyn_client.resources.get.return_value = mock_resource_api

        # Execute
        updateTektonDefinitions(
            dynClient=mock_dyn_client,
            namespace="test-namespace",
            yamlFile="/path/to/test.yaml",
        )

        # Verify
        assert mock_resource_api.apply.call_count == 2
        mock_resource_api.apply.assert_any_call(
            body={
                "apiVersion": "tekton.dev/v1beta1",
                "kind": "Task",
                "metadata": {"name": "test-task", "namespace": "test-namespace"},
                "spec": {},
            },
            namespace="test-namespace",
        )

    @patch("mas.devops.tekton.path.isfile")
    def test_update_tekton_definitions_file_not_found(self, mock_isfile):
        """Test FileNotFoundError when YAML file does not exist."""
        # Setup
        mock_isfile.return_value = False
        mock_dyn_client = MagicMock()

        # Execute and verify
        with pytest.raises(FileNotFoundError) as exc_info:
            updateTektonDefinitions(
                dynClient=mock_dyn_client,
                namespace="test-namespace",
                yamlFile="/path/to/nonexistent.yaml",
            )

        assert "Tekton definitions file not found" in str(exc_info.value)

    @patch("mas.devops.tekton.path.isfile")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.tekton.yaml.safe_load_all")
    def test_update_tekton_definitions_invalid_yaml(self, mock_yaml_load, mock_file, mock_isfile):
        """Test yaml.YAMLError when YAML file is invalid."""
        # Setup
        mock_isfile.return_value = True
        mock_yaml_load.side_effect = yaml.YAMLError("Invalid YAML syntax")
        mock_dyn_client = MagicMock()

        # Execute and verify
        with pytest.raises(yaml.YAMLError):
            updateTektonDefinitions(
                dynClient=mock_dyn_client,
                namespace="test-namespace",
                yamlFile="/path/to/invalid.yaml",
            )

    @patch("mas.devops.tekton.path.isfile")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.tekton.yaml.safe_load_all")
    def test_update_tekton_definitions_multiple_resources(self, mock_yaml_load, mock_file, mock_isfile):
        """Test successful application of multiple resources in single file."""
        # Setup
        mock_isfile.return_value = True
        mock_yaml_load.return_value = [
            {
                "apiVersion": "tekton.dev/v1beta1",
                "kind": "Task",
                "metadata": {"name": "task-1"},
                "spec": {},
            },
            {
                "apiVersion": "tekton.dev/v1beta1",
                "kind": "Task",
                "metadata": {"name": "task-2"},
                "spec": {},
            },
            {
                "apiVersion": "tekton.dev/v1beta1",
                "kind": "Pipeline",
                "metadata": {"name": "pipeline-1"},
                "spec": {},
            },
        ]

        mock_dyn_client = MagicMock()
        mock_resource_api = MagicMock()
        mock_dyn_client.resources.get.return_value = mock_resource_api

        # Execute
        updateTektonDefinitions(
            dynClient=mock_dyn_client,
            namespace="test-namespace",
            yamlFile="/path/to/multi.yaml",
        )

        # Verify
        assert mock_resource_api.apply.call_count == 3

    @patch("mas.devops.tekton.path.isfile")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.tekton.yaml.safe_load_all")
    @patch("mas.devops.tekton.sleep")
    def test_update_tekton_definitions_retry_on_transient_error(self, mock_sleep, mock_yaml_load, mock_file, mock_isfile):
        """Test retry logic on transient API errors."""
        # Setup
        mock_isfile.return_value = True
        mock_yaml_load.return_value = [
            {
                "apiVersion": "tekton.dev/v1beta1",
                "kind": "Task",
                "metadata": {"name": "test-task"},
                "spec": {},
            }
        ]

        mock_dyn_client = MagicMock()
        mock_resource_api = MagicMock()
        mock_dyn_client.resources.get.return_value = mock_resource_api

        # First call fails with 503, second succeeds
        mock_resource_api.apply.side_effect = [
            ApiException(status=503, reason="Service Unavailable"),
            None,
        ]

        # Execute
        updateTektonDefinitions(
            dynClient=mock_dyn_client,
            namespace="test-namespace",
            yamlFile="/path/to/test.yaml",
        )

        # Verify retry occurred
        assert mock_resource_api.apply.call_count == 2
        mock_sleep.assert_called_once()

    @patch("mas.devops.tekton.path.isfile")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.tekton.yaml.safe_load_all")
    def test_update_tekton_definitions_api_exception(self, mock_yaml_load, mock_file, mock_isfile):
        """Test ApiException on non-retryable error."""
        # Setup
        mock_isfile.return_value = True
        mock_yaml_load.return_value = [
            {
                "apiVersion": "tekton.dev/v1beta1",
                "kind": "Task",
                "metadata": {"name": "test-task"},
                "spec": {},
            }
        ]

        mock_dyn_client = MagicMock()
        mock_resource_api = MagicMock()
        mock_dyn_client.resources.get.return_value = mock_resource_api

        # Non-retryable error (e.g., 400 Bad Request)
        mock_resource_api.apply.side_effect = ApiException(status=400, reason="Bad Request")

        # Execute and verify
        with pytest.raises(ApiException) as exc_info:
            updateTektonDefinitions(
                dynClient=mock_dyn_client,
                namespace="test-namespace",
                yamlFile="/path/to/test.yaml",
            )

        assert "Failed to apply Tekton resource" in str(exc_info.value)
