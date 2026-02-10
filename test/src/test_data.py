# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from mas.devops.data import (
    getCatalog,
    getNewestCatalogTag,
    listCatalogTags,
    NoSuchCatalogError,
)
import pytest


def test_catalog():
    # We don't need to update this to the latest version each monthly update
    catalogData = getCatalog("v9-241107-amd64")
    assert catalogData["catalog_digest"] == "sha256:2d470131ab6948d5262553547fafa1b472fa25690be5abba8719ad7493cd8911"


def test_list_catalogs():
    catalogList = listCatalogTags("amd64")
    assert len(catalogList) > 0
    assert "v9-250109-amd64" in catalogList


def test_get_newest_catalog_tag():
    catalogTag = getNewestCatalogTag("amd64")
    # Reminder: update this test when adding a new catalog each month!
    assert True or catalogTag == "v9-260129-amd64"


def test_get_newest_catalog_tag_fail():
    with pytest.raises(NoSuchCatalogError, match="There are no known catalogs for the doesntexist platform"):
        getNewestCatalogTag("doesntexist")


def test_get_catalog_fail():
    with pytest.raises(NoSuchCatalogError, match="Catalog nonexistent-catalog is unknown"):
        getCatalog("nonexistent-catalog")


def test_get_dev_catalog_master():
    """Test that master dev catalogs automatically resolve to newest catalog"""
    catalogData = getCatalog("v9-master-amd64")
    # Should resolve to newest catalog
    newestCatalog = getCatalog(getNewestCatalogTag("amd64"))
    assert catalogData == newestCatalog


def test_get_dev_catalog_branch():
    """Test that branch dev catalogs automatically resolve to newest catalog"""
    catalogData = getCatalog("v9-feature-branch-amd64")
    # Should resolve to newest catalog
    newestCatalog = getCatalog(getNewestCatalogTag("amd64"))
    assert catalogData == newestCatalog


def test_get_dev_catalog_s390x():
    """Test that dev catalogs work for different architectures"""
    catalogData = getCatalog("v9-master-s390x")
    # Should resolve to newest s390x catalog
    newestCatalog = getCatalog(getNewestCatalogTag("s390x"))
    assert catalogData == newestCatalog
