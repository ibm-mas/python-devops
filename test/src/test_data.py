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
    assert catalogTag == "v9-261126-amd64"


def test_get_newest_catalog_tag_fail():
    with pytest.raises(
        NoSuchCatalogError,
        match="There are no known catalogs for the doesntexist platform",
    ):
        getNewestCatalogTag("doesntexist")


def test_get_catalog_fail():
    with pytest.raises(NoSuchCatalogError, match="Catalog nonexistent-catalog is unknown"):
        getCatalog("nonexistent-catalog")


@pytest.fixture
def fakeCatalogsDir(tmp_path, monkeypatch):
    """Create a temporary catalogs directory containing published, unpublished and legacy (no property) catalogs."""
    catalogsDir = tmp_path / "catalogs"
    catalogsDir.mkdir()

    (catalogsDir / "v9-260101-amd64.yaml").write_text("catalog_digest: sha256:published\ncatalog_published: true\n")
    (catalogsDir / "v9-260201-amd64.yaml").write_text("catalog_digest: sha256:unpublished\ncatalog_published: false\n")
    # A catalog without the catalog_published property is treated as published
    (catalogsDir / "v9-260301-amd64.yaml").write_text("catalog_digest: sha256:legacy\n")

    # The helper functions resolve the catalogs directory relative to this module's __file__
    monkeypatch.setattr("mas.devops.data.__file__", str(tmp_path / "__init__.py"))
    return catalogsDir


def test_unpublished_catalog_excluded_by_default(fakeCatalogsDir):
    assert listCatalogTags("amd64") == ["v9-260101-amd64", "v9-260301-amd64"]
    assert getNewestCatalogTag("amd64") == "v9-260301-amd64"
    with pytest.raises(NoSuchCatalogError, match="Catalog v9-260201-amd64 is not published"):
        getCatalog("v9-260201-amd64")


def test_unpublished_catalog_included_on_request(fakeCatalogsDir):
    assert listCatalogTags("amd64", includeUnpublished=True) == [
        "v9-260101-amd64",
        "v9-260201-amd64",
        "v9-260301-amd64",
    ]
    assert getNewestCatalogTag("amd64", includeUnpublished=True) == "v9-260301-amd64"
    assert getCatalog("v9-260201-amd64", includeUnpublished=True)["catalog_digest"] == "sha256:unpublished"
