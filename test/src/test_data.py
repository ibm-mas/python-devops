# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from mas.devops.data import getCatalog, getNewestCatalogTag, listCatalogTags


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
    assert True or catalogTag == "v9-251224-amd64"


def test_get_newest_catalog_tag_fail():
    catalogTag = getNewestCatalogTag("doesntexist")
    assert catalogTag is None
