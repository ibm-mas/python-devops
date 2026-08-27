# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

"""Tests for MCPI Tekton pipeline support functions.

This module covers prepareMcpiPipelinesNamespace() and launchMcpiInstallPipeline()
added to mas.devops.tekton.
"""

import pytest
from unittest.mock import MagicMock, patch, call


class TestPrepareMcpiPipelinesNamespace:
    """Test suite for tekton.prepareMcpiPipelinesNamespace()."""

    @patch("mas.devops.tekton.getStorageClassVolumeBindingMode")
    @patch("mas.devops.tekton.applyResource")
    def test_creates_namespace_rbac_and_pvc(self, mockApply, mockVolumeBindingMode):
        """Test that RBAC ClusterRoleBinding and PVC are created in the correct namespace.

        GIVEN a valid instanceId, storageClass, and accessMode
        WHEN prepareMcpiPipelinesNamespace() is called
        THEN applyResource is called for ClusterRoleBinding and PVC in mcpi-<id>-pipelines.
        """
        from mas.devops.tekton import prepareMcpiPipelinesNamespace

        mockVolumeBindingMode.return_value = "WaitForFirstConsumer"
        mockDynClient = MagicMock()
        mockPvcAPI = MagicMock()
        mockPvcAPI.get.side_effect = Exception("not found")
        mockDynClient.resources.get.return_value = mockPvcAPI

        prepareMcpiPipelinesNamespace(
            dynClient=mockDynClient,
            instanceId="test1",
            storageClass="ocs-storagecluster-cephfs",
            accessMode="ReadWriteMany",
        )

        assert mockApply.call_count == 2
        # First call: ClusterRoleBinding
        crbCall = mockApply.call_args_list[0]
        assert crbCall.kwargs["kind"] == "ClusterRoleBinding"
        assert crbCall.kwargs["namespace"] == "mcpi-test1-pipelines"
        # Second call: PVC
        pvcCall = mockApply.call_args_list[1]
        assert pvcCall.kwargs["kind"] == "PersistentVolumeClaim"
        assert pvcCall.kwargs["namespace"] == "mcpi-test1-pipelines"

    @patch("mas.devops.tekton.getStorageClassVolumeBindingMode")
    @patch("mas.devops.tekton.applyResource")
    def test_skips_rbac_when_configure_rbac_false(self, mockApply, mockVolumeBindingMode):
        """Test that RBAC is not created when configureRBAC=False.

        GIVEN configureRBAC=False
        WHEN prepareMcpiPipelinesNamespace() is called
        THEN only PVC apply is called (not ClusterRoleBinding).
        """
        from mas.devops.tekton import prepareMcpiPipelinesNamespace

        mockVolumeBindingMode.return_value = "WaitForFirstConsumer"
        mockDynClient = MagicMock()
        mockPvcAPI = MagicMock()
        mockPvcAPI.get.side_effect = Exception("not found")
        mockDynClient.resources.get.return_value = mockPvcAPI

        prepareMcpiPipelinesNamespace(
            dynClient=mockDynClient,
            instanceId="test1",
            storageClass="ocs-storagecluster-cephfs",
            accessMode="ReadWriteMany",
            configureRBAC=False,
        )

        assert mockApply.call_count == 1
        pvcCall = mockApply.call_args_list[0]
        assert pvcCall.kwargs["kind"] == "PersistentVolumeClaim"

    @patch("mas.devops.tekton.getStorageClassVolumeBindingMode")
    @patch("mas.devops.tekton.applyResource")
    def test_rbac_template_uses_mcpi_instance_id(self, mockApply, mockVolumeBindingMode):
        """Test that the ClusterRoleBinding body references the mcpi namespace and instance ID.

        GIVEN instanceId='myinst'
        WHEN prepareMcpiPipelinesNamespace() is called
        THEN the ClusterRoleBinding body names use 'mcpi-myinst' prefix.
        """
        from mas.devops.tekton import prepareMcpiPipelinesNamespace

        mockVolumeBindingMode.return_value = "WaitForFirstConsumer"
        mockDynClient = MagicMock()
        mockPvcAPI = MagicMock()
        mockPvcAPI.get.side_effect = Exception("not found")
        mockDynClient.resources.get.return_value = mockPvcAPI

        prepareMcpiPipelinesNamespace(
            dynClient=mockDynClient,
            instanceId="myinst",
            storageClass="gp2",
            accessMode="ReadWriteOnce",
        )

        crbBody = mockApply.call_args_list[0].kwargs["body"]
        assert crbBody["metadata"]["name"] == "mcpi-pipeline-myinst"
        subjects = crbBody["subjects"]
        assert subjects[0]["namespace"] == "mcpi-myinst-pipelines"

    @patch("mas.devops.tekton.getStorageClassVolumeBindingMode")
    @patch("mas.devops.tekton.applyResource")
    def test_pvc_template_uses_mcpi_namespace(self, mockApply, mockVolumeBindingMode):
        """Test that the PVC body is created in the mcpi namespace with the given storage class.

        GIVEN instanceId='inst2' and storageClass='thin'
        WHEN prepareMcpiPipelinesNamespace() is called
        THEN the PVC body has namespace mcpi-inst2-pipelines and storageClassName thin.
        """
        from mas.devops.tekton import prepareMcpiPipelinesNamespace

        mockVolumeBindingMode.return_value = "WaitForFirstConsumer"
        mockDynClient = MagicMock()
        mockPvcAPI = MagicMock()
        mockPvcAPI.get.side_effect = Exception("not found")
        mockDynClient.resources.get.return_value = mockPvcAPI

        prepareMcpiPipelinesNamespace(
            dynClient=mockDynClient,
            instanceId="inst2",
            storageClass="thin",
            accessMode="ReadWriteOnce",
        )

        pvcBody = mockApply.call_args_list[1].kwargs["body"]
        assert pvcBody["metadata"]["namespace"] == "mcpi-inst2-pipelines"
        assert pvcBody["spec"]["storageClassName"] == "thin"
        assert pvcBody["spec"]["accessModes"] == ["ReadWriteOnce"]


class TestLaunchMcpiInstallPipeline:
    """Test suite for tekton.launchMcpiInstallPipeline()."""

    @patch("mas.devops.tekton.getConsoleURL")
    @patch("mas.devops.tekton.launchPipelineRun")
    def test_launches_in_mcpi_namespace(self, mockLaunchPipelineRun, mockGetConsoleURL):
        """Test that the pipeline run is launched in the mcpi-<id>-pipelines namespace.

        GIVEN params with mas_instance_id='inst1'
        WHEN launchMcpiInstallPipeline() is called
        THEN launchPipelineRun is called with namespace=mcpi-inst1-pipelines.
        """
        from mas.devops.tekton import launchMcpiInstallPipeline

        mockLaunchPipelineRun.return_value = "260101-1200"
        mockGetConsoleURL.return_value = "https://console.example.com"
        mockDynClient = MagicMock()

        launchMcpiInstallPipeline(
            dynClient=mockDynClient,
            params={"mas_instance_id": "inst1", "mcpi_channel": "v9.2"},
        )

        mockLaunchPipelineRun.assert_called_once_with(
            mockDynClient,
            "mcpi-inst1-pipelines",
            "pipelinerun-mcpi-install",
            {"mas_instance_id": "inst1", "mcpi_channel": "v9.2"},
        )

    @patch("mas.devops.tekton.getConsoleURL")
    @patch("mas.devops.tekton.launchPipelineRun")
    def test_returns_console_url(self, mockLaunchPipelineRun, mockGetConsoleURL):
        """Test that the returned URL points to the correct PipelineRun in the OCP console.

        GIVEN params with mas_instance_id='inst1' and a known timestamp
        WHEN launchMcpiInstallPipeline() is called
        THEN the returned URL contains the instance ID, namespace, and timestamp.
        """
        from mas.devops.tekton import launchMcpiInstallPipeline

        mockLaunchPipelineRun.return_value = "260101-1200"
        mockGetConsoleURL.return_value = "https://console.example.com"
        mockDynClient = MagicMock()

        url = launchMcpiInstallPipeline(
            dynClient=mockDynClient,
            params={"mas_instance_id": "inst1", "mcpi_channel": "v9.2"},
        )

        assert url == (
            "https://console.example.com/k8s/ns/mcpi-inst1-pipelines"
            "/tekton.dev~v1beta1~PipelineRun/inst1-install-260101-1200"
        )

    @patch("mas.devops.tekton.getConsoleURL")
    @patch("mas.devops.tekton.launchPipelineRun")
    def test_uses_pipelinerun_mcpi_install_template(self, mockLaunchPipelineRun, mockGetConsoleURL):
        """Test that the correct pipelinerun template name is used.

        GIVEN any valid params
        WHEN launchMcpiInstallPipeline() is called
        THEN launchPipelineRun is called with templateName='pipelinerun-mcpi-install'.
        """
        from mas.devops.tekton import launchMcpiInstallPipeline

        mockLaunchPipelineRun.return_value = "260101-0900"
        mockGetConsoleURL.return_value = "https://console.example.com"
        mockDynClient = MagicMock()

        launchMcpiInstallPipeline(
            dynClient=mockDynClient,
            params={"mas_instance_id": "dev1", "mcpi_channel": "v9.3"},
        )

        _, args, _ = mockLaunchPipelineRun.mock_calls[0]
        templateName = args[2]
        assert templateName == "pipelinerun-mcpi-install"
