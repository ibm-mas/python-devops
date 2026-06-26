# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from mas.devops import utils


def test_version_before():
    assert utils.isVersionBefore("9.1.0", "9.1.x-feature") is False
    assert utils.isVersionBefore("9.1.0", "9.0.0") is True
    assert utils.isVersionBefore("8.11.1", "9.1.0") is False
    assert utils.isVersionBefore("9.1.0", "9.1.x-stable") is False


def test_version_equal_of_after():
    assert utils.isVersionEqualOrAfter("9.1.0", "9.2.x-feature") is True
    assert utils.isVersionEqualOrAfter("9.1.0", "9.0.0") is False
    assert utils.isVersionEqualOrAfter("8.11.1", "9.1.0") is True
    assert utils.isVersionEqualOrAfter("9.2.0", "9.1.x-stable") is False
