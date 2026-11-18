# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from unittest.mock import MagicMock, patch

import pytest

from mas.devops.mas import getDefaultStorageClasses


def _make_storage_classes(*names):
    """Build StorageClass-like mocks for the given names."""
    storageClasses = []
    for name in names:
        sc = MagicMock()
        sc.metadata.name = name
        storageClasses.append(sc)
    return storageClasses


@pytest.mark.parametrize(
    "available,provider,rwo,rwx",
    [
        (["gp2-csi", "gp3-csi", "efs"], "aws", "gp3-csi", "efs"),
        (["ibmc-block-gold", "ibmc-file-gold-gid"], "ibmc", "ibmc-block-gold", "ibmc-file-gold-gid"),
        (["ibmc-vpc-block-10iops-tier", "ibmc-vpc-file-1000-iops"], "ibmc-vpc", "ibmc-vpc-block-10iops-tier", "ibmc-vpc-file-1000-iops"),
        (["ocs-storagecluster-cephfs", "ocs-storagecluster-ceph-rbd"], "ocs", "ocs-storagecluster-ceph-rbd", "ocs-storagecluster-cephfs"),
        (
            ["ocs-external-storagecluster-ceph-rbd", "ocs-external-storagecluster-cephfs"],
            "ocs-external",
            "ocs-external-storagecluster-ceph-rbd",
            "ocs-external-storagecluster-cephfs",
        ),
        (["longhorn"], "longhorn", "longhorn", "longhorn"),
        (["nfs-client"], "nfs", "nfs-client", "nfs-client"),
        (["managed-premium", "azurefiles-premium"], "azure", "managed-premium", "azurefiles-premium"),
    ],
)
def test_provider_detected_when_all_classes_exist(available, provider, rwo, rwx):
    """Test that a provider is detected when all of its storage classes exist.

    GIVEN a cluster containing every storage class for a known provider
    WHEN getDefaultStorageClasses() runs
    THEN the provider and its RWO/RWX classes are returned.
    """
    with patch("mas.devops.mas.suite.getStorageClasses", return_value=_make_storage_classes(*available)):
        result = getDefaultStorageClasses(MagicMock())

    assert result.provider == provider
    assert result.rwo == rwo
    assert result.rwx == rwx


@pytest.mark.parametrize(
    "available",
    [
        ["gp2-csi", "gp3-csi"],
        ["efs"],
        ["ibmc-block-gold"],
        ["ibmc-file-gold-gid"],
        ["ibmc-vpc-block-10iops-tier"],
        ["ocs-storagecluster-ceph-rbd"],
        ["ocs-external-storagecluster-cephfs"],
        ["managed-premium"],
        ["azurefiles-premium"],
    ],
)
def test_provider_not_detected_when_pair_incomplete(available):
    """Test that a partially present storage class pair is not detected as a provider.

    GIVEN a cluster containing only one storage class of a provider's RWO/RWX pair
    WHEN getDefaultStorageClasses() runs
    THEN no provider is detected, e.g. AWS without the EFS CSI driver (ibm-mas/cli#1520).
    """
    with patch("mas.devops.mas.suite.getStorageClasses", return_value=_make_storage_classes(*available)):
        result = getDefaultStorageClasses(MagicMock())

    assert result.provider is None
    assert result.providerName is None
    assert result.rwo is None
    assert result.rwx is None


def test_no_storage_classes():
    """Test that nothing is detected on a cluster without storage classes.

    GIVEN a cluster with no storage classes
    WHEN getDefaultStorageClasses() runs
    THEN no provider is detected.
    """
    with patch("mas.devops.mas.suite.getStorageClasses", return_value=[]):
        result = getDefaultStorageClasses(MagicMock())

    assert result.provider is None
