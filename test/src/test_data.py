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
    catalogData = getCatalog("v9-241205-amd64")
    assert catalogData["catalog_digest"] == "sha256:31e2ce74568ace657e121fa0a97d9499942437e9e4807b31d2e64e2a079c4cf8"


def test_list_catalogs():
    catalogList = listCatalogTags("amd64")
    assert len(catalogList) > 0
    assert "v9-241205-amd64" in catalogList


def test_get_newest_catalog_tag():
    catalogTag = getNewestCatalogTag("amd64")
    # Reminder: update this test when adding a new catalog each month!
    assert catalogTag == "v9-241205-amd64"


def test_get_newest_catalog_tag_fail():
    catalogTag = getNewestCatalogTag("doesntexist")
    assert catalogTag is None
