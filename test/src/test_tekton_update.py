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
from jinja2 import Environment, FileSystemLoader
from kubernetes.dynamic.exceptions import ApiException
from os import path

from mas.devops.tekton import updateTektonDefinitions, launchUpdatePipeline, launchUpgradePipeline, launchAiServiceUpgradePipeline


class TestUpdateTektonDefinitions:
    """Test suite for tekton.updateTektonDefinitions() function."""

    @patch("mas.devops.tekton.applyResource")
    @patch("mas.devops.tekton.path.isfile")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.tekton.yaml.safe_load_all")
    def test_update_tekton_definitions_success(self, mock_yaml_load, mock_file, mock_isfile, mock_apply):
        """Test successful application of Tekton resources."""
        # Setup
        mock_isfile.return_value = True
        mock_yaml_load.return_value = [
            {
                "apiVersion": "tekton.dev/v1",
                "kind": "Task",
                "metadata": {"name": "test-task"},
                "spec": {},
            },
            {
                "apiVersion": "tekton.dev/v1",
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
        assert mock_apply.call_count == 2

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

    @patch("mas.devops.tekton.applyResource")
    @patch("mas.devops.tekton.path.isfile")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.tekton.yaml.safe_load_all")
    def test_update_tekton_definitions_multiple_resources(self, mock_yaml_load, mock_file, mock_isfile, mock_apply):
        """Test successful application of multiple resources in single file."""
        # Setup
        mock_isfile.return_value = True
        mock_yaml_load.return_value = [
            {
                "apiVersion": "tekton.dev/v1",
                "kind": "Task",
                "metadata": {"name": "task-1"},
                "spec": {},
            },
            {
                "apiVersion": "tekton.dev/v1",
                "kind": "Task",
                "metadata": {"name": "task-2"},
                "spec": {},
            },
            {
                "apiVersion": "tekton.dev/v1",
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
        assert mock_apply.call_count == 3

    @patch("mas.devops.tekton.applyResource")
    @patch("mas.devops.tekton.path.isfile")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.tekton.yaml.safe_load_all")
    @patch("mas.devops.tekton.sleep")
    def test_update_tekton_definitions_retry_on_transient_error(self, mock_sleep, mock_yaml_load, mock_file, mock_isfile, mock_apply):
        """Test retry logic on transient API errors."""
        # Setup
        mock_isfile.return_value = True
        mock_yaml_load.return_value = [
            {
                "apiVersion": "tekton.dev/v1",
                "kind": "Task",
                "metadata": {"name": "test-task"},
                "spec": {},
            }
        ]

        mock_dyn_client = MagicMock()
        mock_resource_api = MagicMock()
        mock_dyn_client.resources.get.return_value = mock_resource_api

        # First call fails with 503, second succeeds
        mock_apply.side_effect = [
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
        assert mock_apply.call_count == 2
        mock_sleep.assert_called_once()

    @patch("mas.devops.tekton.applyResource")
    @patch("mas.devops.tekton.path.isfile")
    @patch("builtins.open", new_callable=mock_open)
    @patch("mas.devops.tekton.yaml.safe_load_all")
    def test_update_tekton_definitions_api_exception(self, mock_yaml_load, mock_file, mock_isfile, mock_apply):
        """Test ApiException on non-retryable error."""
        # Setup
        mock_isfile.return_value = True
        mock_yaml_load.return_value = [
            {
                "apiVersion": "tekton.dev/v1",
                "kind": "Task",
                "metadata": {"name": "test-task"},
                "spec": {},
            }
        ]

        mock_dyn_client = MagicMock()
        mock_resource_api = MagicMock()
        mock_dyn_client.resources.get.return_value = mock_resource_api

        # Non-retryable error (e.g., 400 Bad Request)
        mock_apply.side_effect = ApiException(status=400, reason="Bad Request")

        # Execute and verify
        with pytest.raises(ApiException) as exc_info:
            updateTektonDefinitions(
                dynClient=mock_dyn_client,
                namespace="test-namespace",
                yamlFile="/path/to/test.yaml",
            )

        assert "Failed to apply Tekton resource" in str(exc_info.value)


class TestLaunchUpdatePipelineDb2uKind:
    """Test suite for the db2u_kind parameter rendered by tekton.launchUpdatePipeline()."""

    @staticmethod
    def _launch(extra_params):
        params = {
            "mas_catalog_version": "v9-260902-amd64",
            "db2_namespace": "db2u",
            "db2_channel": "v120105.0",
            "db2_v12_upgrade": "true",
        }
        params.update(extra_params)
        with patch("mas.devops.tekton.applyResource") as mock_apply, patch("mas.devops.tekton.getConsoleURL", return_value="https://console"):
            launchUpdatePipeline(dynClient=MagicMock(), params=params)
        body = mock_apply.call_args.kwargs["body"]
        return {p["name"]: p["value"] for p in body["spec"]["params"]}

    @pytest.mark.parametrize("kind", ["db2uinstance", "db2ucluster"])
    def test_db2u_kind_is_passed_to_pipelinerun(self, kind):
        """db2u_kind is rendered into the PipelineRun params when provided."""
        assert self._launch({"db2u_kind": kind})["db2u_kind"] == kind

    def test_db2u_kind_omitted_when_not_provided(self):
        """db2u_kind is not rendered when it is not provided, preserving existing behaviour."""
        assert "db2u_kind" not in self._launch({})

    def test_db2u_kind_omitted_when_empty(self):
        """db2u_kind is not rendered when it is an empty string."""
        assert "db2u_kind" not in self._launch({"db2u_kind": ""})

    def test_db2u_kind_omitted_without_db2_namespace(self):
        """db2u_kind is only rendered as part of the Db2 update block."""
        assert "db2u_kind" not in self._launch({"db2_namespace": "", "db2u_kind": "db2uinstance"})


class TestPipelineRunOlmApprovalParams:
    """Test suite for the OLM approval params rendered into the install, update and upgrade PipelineRuns.

    The params are conditionally emitted: present when set, omitted when unset
    or empty (in which case the pipeline's own defaults apply). The update
    path is additionally exercised through launchUpdatePipeline() to prove the
    params survive the **params passthrough.
    """

    TEMPLATE_DIR = path.join(path.abspath(path.dirname(__file__)), "..", "..", "src", "mas", "devops", "templates")

    @staticmethod
    def _render(templateName, extraParams):
        env = Environment(loader=FileSystemLoader(searchpath=TestPipelineRunOlmApprovalParams.TEMPLATE_DIR))
        template = env.get_template(templateName)
        rendered = template.render(**extraParams)
        return {p["name"]: p["value"] for p in yaml.safe_load(rendered)["spec"]["params"]}

    @pytest.mark.parametrize(
        "template,baseParams",
        [
            ("pipelinerun-install.yml.j2", {"mas_instance_id": "inst1", "aiservice_instance_id": ""}),
            ("pipelinerun-update.yml.j2", {"mas_catalog_version": "v9-260902-amd64"}),
            ("pipelinerun-upgrade.yml.j2", {"mas_instance_id": "inst1", "mas_channel": "9.2.x"}),
        ],
    )
    def test_olm_params_emitted_when_set(self, template, baseParams):
        """olm_approval_mode and olm_approval_timeout are rendered when provided."""
        params = self._render(template, {**baseParams, "olm_approval_mode": "Manual", "olm_approval_timeout": "300"})
        assert params["olm_approval_mode"] == "Manual"
        assert params["olm_approval_timeout"] == "300"

    @pytest.mark.parametrize(
        "template,baseParams",
        [
            ("pipelinerun-install.yml.j2", {"mas_instance_id": "inst1", "aiservice_instance_id": ""}),
            ("pipelinerun-update.yml.j2", {"mas_catalog_version": "v9-260902-amd64"}),
            ("pipelinerun-upgrade.yml.j2", {"mas_instance_id": "inst1", "mas_channel": "9.2.x"}),
        ],
    )
    def test_olm_params_omitted_when_unset(self, template, baseParams):
        """Neither param is rendered when not provided, preserving existing behaviour."""
        params = self._render(template, baseParams)
        assert "olm_approval_mode" not in params
        assert "olm_approval_timeout" not in params

    @pytest.mark.parametrize(
        "template,baseParams",
        [
            ("pipelinerun-install.yml.j2", {"mas_instance_id": "inst1", "aiservice_instance_id": ""}),
            ("pipelinerun-update.yml.j2", {"mas_catalog_version": "v9-260902-amd64"}),
            ("pipelinerun-upgrade.yml.j2", {"mas_instance_id": "inst1", "mas_channel": "9.2.x"}),
        ],
    )
    def test_olm_params_omitted_when_empty(self, template, baseParams):
        """An empty string is treated as unset, matching the other optional params."""
        params = self._render(template, {**baseParams, "olm_approval_mode": "", "olm_approval_timeout": ""})
        assert "olm_approval_mode" not in params
        assert "olm_approval_timeout" not in params

    @staticmethod
    def _launchUpdate(extraParams):
        params = {"mas_catalog_version": "v9-260902-amd64"}
        params.update(extraParams)
        with patch("mas.devops.tekton.applyResource") as mock_apply, patch("mas.devops.tekton.getConsoleURL", return_value="https://console"):
            launchUpdatePipeline(dynClient=MagicMock(), params=params)
        body = mock_apply.call_args.kwargs["body"]
        return {p["name"]: p["value"] for p in body["spec"]["params"]}

    def test_update_pipelinerun_carries_olm_params(self):
        """The olm params pass through launchUpdatePipeline's **params into the PipelineRun."""
        params = self._launchUpdate({"olm_approval_mode": "Manual", "olm_approval_timeout": "600"})
        assert params["olm_approval_mode"] == "Manual"
        assert params["olm_approval_timeout"] == "600"

    def test_update_pipelinerun_omits_unset_olm_params(self):
        """launchUpdatePipeline without the olm params renders a PipelineRun without them."""
        params = self._launchUpdate({})
        assert "olm_approval_mode" not in params
        assert "olm_approval_timeout" not in params


class TestLaunchUpgradePipeline:
    """Test suite for the params-only launchUpgradePipeline() signature.

    ``params`` is the definitive list of PipelineRun params, rendered verbatim
    (matching launchUpdatePipeline / launchRestorePipeline).  The upgrade TUI
    writes the instance-selection field into params, so ``mas_instance_id``
    arrives via params — the previous explicit-argument form raised
    ``TypeError: render() got multiple values for keyword argument
    'mas_instance_id'`` at the PipelineRun submission step.
    """

    @staticmethod
    def _launchUpgrade(params):
        with patch("mas.devops.tekton.applyResource") as mock_apply, patch("mas.devops.tekton.getConsoleURL", return_value="https://console"):
            launchUpgradePipeline(dynClient=MagicMock(), params=params)
        body = mock_apply.call_args.kwargs["body"]
        return body, {p["name"]: p["value"] for p in body["spec"]["params"]}

    def test_upgrade_pipelinerun_renders_params_verbatim(self):
        """Every entry in params is rendered into the PipelineRun, keyed off mas_instance_id."""
        body, params = self._launchUpgrade(
            {
                "mas_instance_id": "inst1",
                "mas_channel": "9.0.x",
                "skip_pre_check": "false",
                "storage_class_rwo": "rwo-class",
            }
        )
        assert body["metadata"]["name"].startswith("inst1-upgrade-")
        assert params["mas_instance_id"] == "inst1"
        assert params["mas_channel"] == "9.0.x"
        assert params["skip_pre_check"] == "false"
        assert params["storage_class_rwo"] == "rwo-class"

    def test_upgrade_pipelinerun_minimal_params(self):
        """Only mas_instance_id is required; the other upgrade params default in the pipeline."""
        body, params = self._launchUpgrade({"mas_instance_id": "inst1"})
        assert body["metadata"]["name"].startswith("inst1-upgrade-")
        assert params["mas_instance_id"] == "inst1"
        assert params["mas_channel"] == ""
        assert "skip_pre_check" not in params
        assert "storage_class_rwo" not in params

    def test_aiservice_upgrade_pipelinerun_renders_params_verbatim(self):
        """launchAiServiceUpgradePipeline renders params verbatim, keyed off aiservice_instance_id."""
        with patch("mas.devops.tekton.applyResource") as mock_apply, patch("mas.devops.tekton.getConsoleURL", return_value="https://console"):
            launchAiServiceUpgradePipeline(
                dynClient=MagicMock(),
                params={
                    "aiservice_instance_id": "inst1",
                    "aiservice_channel": "9.0.x",
                    "skip_pre_check": "true",
                },
            )
        body = mock_apply.call_args.kwargs["body"]
        params = {p["name"]: p["value"] for p in body["spec"]["params"]}
        assert body["metadata"]["name"].startswith("inst1-upgrade-")
        assert params["aiservice_instance_id"] == "inst1"
        assert params["aiservice_channel"] == "9.0.x"
        assert params["skip_pre_check"] == "true"
