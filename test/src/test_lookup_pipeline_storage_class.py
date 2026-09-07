# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from unittest.mock import MagicMock
from kubernetes.dynamic.exceptions import NotFoundError

from mas.devops.tekton import lookupPipelineStorageClass


def _make_pvc(storage_class, access_modes):
    """Build a minimal ResourceInstance-like mock for a PVC."""
    pvc = MagicMock()
    pvc.spec.storageClassName = storage_class
    pvc.spec.accessModes = access_modes
    return pvc


def _make_dyn_client(pvc=None, raise_exc=None):
    """Build a DynamicClient mock that returns the given PVC or raises raise_exc."""
    pvc_api = MagicMock()
    if raise_exc is not None:
        pvc_api.get.side_effect = raise_exc
    else:
        pvc_api.get.return_value = pvc
    dyn_client = MagicMock()
    dyn_client.resources.get.return_value = pvc_api
    return dyn_client


class TestLookupPipelineStorageClass:
    """Tests for tekton.lookupPipelineStorageClass()"""

    def test_returns_storage_class_and_access_mode_from_existing_pvc(self):
        """Normal upgrade path: config-pvc already exists with a known storage class."""
        pvc = _make_pvc("ibmc-file-gold-gid", ["ReadWriteMany"])
        dyn_client = _make_dyn_client(pvc=pvc)

        sc, mode = lookupPipelineStorageClass(dyn_client, "inst1")

        assert sc == "ibmc-file-gold-gid"
        assert mode == "ReadWriteMany"
        dyn_client.resources.get.assert_called_once_with(api_version="v1", kind="PersistentVolumeClaim")
        dyn_client.resources.get.return_value.get.assert_called_once_with(name="config-pvc", namespace="mas-inst1-pipelines")

    def test_returns_rwo_access_mode_for_sno_pvc(self):
        """SNO cluster: config-pvc uses ReadWriteOnce."""
        pvc = _make_pvc("ocs-storagecluster-cephfs", ["ReadWriteOnce"])
        dyn_client = _make_dyn_client(pvc=pvc)

        sc, mode = lookupPipelineStorageClass(dyn_client, "mas1")

        assert sc == "ocs-storagecluster-cephfs"
        assert mode == "ReadWriteOnce"

    def test_returns_none_none_when_pvc_not_found(self):
        """No config-pvc in namespace (MAS not installed via CLI): returns (None, None)."""
        http_response = MagicMock()
        http_response.status = 404
        http_response.reason = "Not Found"
        http_response.data = b'{"reason":"NotFound"}'
        not_found = NotFoundError(http_response)
        dyn_client = _make_dyn_client(raise_exc=not_found)

        sc, mode = lookupPipelineStorageClass(dyn_client, "inst1")

        assert sc is None
        assert mode is None

    def test_returns_none_none_when_response_is_not_a_resource_instance(self):
        """API returns a plain dict instead of a ResourceInstance (e.g. in unit tests)."""
        pvc_api = MagicMock()
        pvc_api.get.return_value = {"kind": "PersistentVolumeClaim"}  # plain dict, no .spec
        dyn_client = MagicMock()
        dyn_client.resources.get.return_value = pvc_api

        sc, mode = lookupPipelineStorageClass(dyn_client, "inst1")

        assert sc is None
        assert mode is None

    def test_returns_none_access_mode_when_access_modes_list_is_empty(self):
        """PVC exists but accessModes list is empty: access mode returns None."""
        pvc = _make_pvc("standard", [])
        dyn_client = _make_dyn_client(pvc=pvc)

        sc, mode = lookupPipelineStorageClass(dyn_client, "inst1")

        assert sc == "standard"
        assert mode is None

    def test_namespace_is_derived_from_instance_id(self):
        """The lookup targets the correct pipelines namespace for the given instance ID."""
        pvc = _make_pvc("thin", ["ReadWriteOnce"])
        dyn_client = _make_dyn_client(pvc=pvc)

        lookupPipelineStorageClass(dyn_client, "myinst")

        dyn_client.resources.get.return_value.get.assert_called_once_with(name="config-pvc", namespace="mas-myinst-pipelines")
