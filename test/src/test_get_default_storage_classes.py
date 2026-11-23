# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from types import SimpleNamespace

from mas.devops.mas.suite import getDefaultStorageClasses


def _make_storage_classes(*names):
    """Build minimal ResourceInstance-like mocks for the named storage classes."""
    return [SimpleNamespace(metadata=SimpleNamespace(name=name)) for name in names]


def _detect(monkeypatch, *existingNames):
    """Run getDefaultStorageClasses against a cluster containing only the named storage classes."""
    monkeypatch.setattr("mas.devops.mas.suite.getStorageClasses", lambda dynClient: _make_storage_classes(*existingNames))
    return getDefaultStorageClasses(None)


class TestGetDefaultStorageClasses:
    """Tests for mas.devops.mas.suite.getDefaultStorageClasses()"""

    def test_detects_aws_when_both_gp3_csi_and_efs_exist(self, monkeypatch):
        """AWS cluster with the full pair of storage classes: provider is detected."""
        result = _detect(monkeypatch, "gp2-csi", "gp3-csi", "efs")

        assert result.provider == "aws"
        assert result.providerName == "AWS GP3"
        assert result.rwo == "gp3-csi"
        assert result.rwx == "efs"

    def test_no_detection_when_only_ebs_classes_exist(self, monkeypatch):
        """Issue ibm-mas/cli#1520: AWS cluster with only gp2-csi/gp3-csi must not report efs."""
        result = _detect(monkeypatch, "gp2-csi", "gp3-csi")

        assert result.provider is None
        assert result.providerName is None
        assert result.rwo is None
        assert result.rwx is None

    def test_no_detection_when_only_rwx_class_of_a_pair_exists(self, monkeypatch):
        """efs without gp3-csi: the old either-name matching would have detected AWS."""
        result = _detect(monkeypatch, "efs")

        assert result.provider is None
        assert result.rwo is None
        assert result.rwx is None

    def test_no_detection_when_only_rwo_class_of_a_pair_exists(self, monkeypatch):
        """gp3-csi without efs: no provider is detected."""
        result = _detect(monkeypatch, "gp3-csi")

        assert result.provider is None
        assert result.rwo is None
        assert result.rwx is None

    def test_detects_ibmc_when_both_classes_exist(self, monkeypatch):
        """IBM Cloud ROKS classic cluster with the full pair of storage classes."""
        result = _detect(monkeypatch, "ibmc-block-gold", "ibmc-file-gold-gid")

        assert result.provider == "ibmc"
        assert result.providerName == "IBMCloud ROKS Classic"
        assert result.rwo == "ibmc-block-gold"
        assert result.rwx == "ibmc-file-gold-gid"

    def test_detects_single_class_provider(self, monkeypatch):
        """longhorn provides both RWO and RWX via a single storage class."""
        result = _detect(monkeypatch, "longhorn")

        assert result.provider == "longhorn"
        assert result.providerName == "Longhorn"
        assert result.rwo == "longhorn"
        assert result.rwx == "longhorn"

    def test_no_detection_when_classes_from_different_providers_are_mixed(self, monkeypatch):
        """gp3-csi (AWS RWO) plus ibmc-file-gold-gid (IBM Cloud RWX) is not any provider."""
        result = _detect(monkeypatch, "gp3-csi", "ibmc-file-gold-gid")

        assert result.provider is None
        assert result.rwo is None
        assert result.rwx is None

    def test_no_detection_when_no_storage_classes_exist(self, monkeypatch):
        """Cluster with no storage classes at all."""
        result = _detect(monkeypatch)

        assert result.provider is None
        assert result.rwo is None
        assert result.rwx is None

    def test_unrecognized_storage_classes_are_ignored(self, monkeypatch):
        """Cluster with only unknown storage class names."""
        result = _detect(monkeypatch, "standard", "thin", "topolvm-provisioner")

        assert result.provider is None
        assert result.rwo is None
        assert result.rwx is None

    def test_earlier_provider_in_table_wins_when_multiple_providers_are_complete(self, monkeypatch):
        """Matching is deterministic: the first complete provider in KNOWN_STORAGE_PROVIDERS wins."""
        result = _detect(monkeypatch, "gp3-csi", "efs", "ocs-storagecluster-ceph-rbd", "ocs-storagecluster-cephfs")

        assert result.provider == "ocs"
