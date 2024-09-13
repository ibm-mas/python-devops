# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

import pytest

from mas.devops import db2

@pytest.mark.parametrize("cr_k,cr_v,pod_v,expected", [
  ("MIRRORLOGPATH", "/mnt/backup/MIRRORLOGPATH", "/mnt/backup/MIRRORLOGPATH/NODE0000/LOGSTREAM0000/", True),
  ("MIRRORLOGPATH", "/mnt/backup/MIRRORLOGPATH", "/notcorrect/NODE0000/LOGSTREAM0000/", False),
  ("NOTSPECIAL", "/mnt/backup/MIRRORLOGPATH", "/mnt/backup/MIRRORLOGPATH/NODE0000/LOGSTREAM0000/", False),

  ("X", "22 AUTOMATIC", "AUTOMATIC(22)", True),
  ("X", "22 AUTOMATIC", "AUTOMATIC(44)", False),
  ("X", "AUTOMATIC", "AUTOMATIC(22)", True),
  ("X", "automatic", "AUTOMATIC(22)", True),
  ("X", "automatic", "AUTOMATIC", True),
  ("X", "automaticx", "AUTOMATIC", False),

  ("X", "otherSTRING", "otherSTRING", True),
  ("X", "otherSTRING", "OTHERstring", False),

  ("X", "other string", "other string", True),

  ("X", "22", "22", True),

])
def test_cr_pod_v_matches(cr_k, cr_v, pod_v, expected):
  assert( db2.cr_pod_v_matches(cr_k, cr_v, pod_v) is expected )

def test_validate_db2_config():
  pass