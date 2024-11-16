# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from mas.devops.data import getCatalog


def test_catalog():
    catalogData = getCatalog("v9-241107-amd64")
    assert catalogData["catalog_digest"] == "sha256:2d470131ab6948d5262553547fafa1b472fa25690be5abba8719ad7493cd8911"
