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
    assert catalogTag == "v9-260625-amd64"


def test_get_newest_catalog_tag_fail():
    with pytest.raises(
        NoSuchCatalogError,
        match="There are no known catalogs for the doesntexist platform",
    ):
        getNewestCatalogTag("doesntexist")


def test_get_catalog_fail():
    with pytest.raises(NoSuchCatalogError, match="Catalog nonexistent-catalog is unknown"):
        getCatalog("nonexistent-catalog")


# ---------------------------------------------------------------------------
# Dev / rolling catalog tests
# ---------------------------------------------------------------------------


def test_get_dev_catalog_v9_master_amd64():
    """getCatalog() for v9-master-amd64 returns a minimal CatalogSource dict."""
    catalog = getCatalog("v9-master-amd64")
    assert catalog["kind"] == "CatalogSource"
    assert "v9-master-amd64" in catalog["spec"]["image"]


def test_get_dev_catalog_v9_master_s390x():
    """getCatalog() for v9-master-s390x also resolves as a dev catalog."""
    catalog = getCatalog("v9-master-s390x")
    assert catalog["kind"] == "CatalogSource"
    assert "v9-master-s390x" in catalog["spec"]["image"]


def test_get_dev_catalog_contains_expected_keys():
    """Dev catalog descriptor contains the expected top-level keys."""
    catalog = getCatalog("v9-master-amd64")
    assert "apiVersion" in catalog
    assert "kind" in catalog
    assert "metadata" in catalog
    assert "spec" in catalog


def test_get_dev_catalog_does_not_raise_no_such_catalog_error():
    """Rolling dev catalog IDs must NOT raise NoSuchCatalogError."""
    try:
        getCatalog("v9-master-amd64")
    except NoSuchCatalogError:
        pytest.fail("getCatalog('v9-master-amd64') raised NoSuchCatalogError unexpectedly")
