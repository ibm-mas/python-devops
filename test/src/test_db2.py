# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

import os
import pytest
import yaml


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



def test_check_db_cfgs_no_spec():
  with pytest.raises(Exception, match="spec.environment.databases not found or empty"):
    db2.check_db_cfgs(
      dict(
      ), None, None, None
    )

def test_check_db_cfgs_no_environment():
  with pytest.raises(Exception, match="spec.environment.databases not found or empty"):
    db2.check_db_cfgs(
      dict(
        spec=dict()
      ), None, None, None
    )

def test_check_db_cfgs_no_databases():
  with pytest.raises(Exception, match="spec.environment.databases not found or empty"):
    db2.check_db_cfgs(
      dict(
        spec=dict(
          environment=dict()
        )
      ), None, None, None
    )

def test_check_db_cfgs(mocker):
  '''
  Verifies that check_db_cfg function is called for each db in list
  '''

  mock_CoreV1Api = mocker.patch('kubernetes.client.CoreV1Api')
  mock_core_v1_api = mock_CoreV1Api.return_value

  mock_check_db_cfg = mocker.patch("mas.devops.db2.check_db_cfg")

  db2.check_db_cfgs(
    dict(
      spec=dict(
        environment=dict(
          databases = [
            dict(name="a"), dict(name="b")
          ]
        )
      )
    ), mock_core_v1_api, "mas_instance_id", "mas_app_id"
  )


  assert mock_check_db_cfg.call_args_list == [
    mocker.call( dict(name="a"), mock_core_v1_api, "mas_instance_id", "mas_app_id"),
    mocker.call( dict(name="b"), mock_core_v1_api, "mas_instance_id", "mas_app_id")
  ]


def test_check_db_cfg_no_dbConfig(mocker):
  mocker.patch("mas.devops.db2.db2_pod_exec_db2_get_db_cfg")
  assert db2.check_db_cfg(dict(name="a"), None, None, None) == []

def test_check_db_cfg_empty_dbConfig(mocker):
  mocker.patch("mas.devops.db2.db2_pod_exec_db2_get_db_cfg")
  assert db2.check_db_cfg(dict(name="a", dbConfig=[]), None, None, None) == []


def test_check_db_cfg(mocker):

  mock_db2_pod_exec_db2_get_db_cfg = mocker.patch("mas.devops.db2.db2_pod_exec_db2_get_db_cfg")
  mock_db2_pod_exec_db2_get_db_cfg.return_value = '''
    Default application heap (4KB)             (APPLHEAPSZ) = AUTOMATIC(8192)
    Changed pages threshold                (CHNGPGS_THRESH) = 80
  '''
  db_name = "MYDB"
  db = dict(
    name=db_name, 
    dbConfig=dict(
      APPLHEAPSZ="8192 AUTOMATIC",
      NOTFOUNDINOUTPUT="XXX",
      CHNGPGS_THRESH="40"
    )
  )

  assert set(db2.check_db_cfg(db, None, None, None)) == set([
    f"[db cfg for {db_name}] NOTFOUNDINOUTPUT not found in output of db2 get db cfg command",
    f"[db cfg for {db_name}] CHNGPGS_THRESH: 40 != 80"
  ])



def test_validate_db2_config(mocker):

  current_dir = os.path.dirname(os.path.abspath(__file__))

  mock_get_db2u_instance_cr = mocker.patch("mas.devops.db2.get_db2u_instance_cr")
  with open(os.path.join(current_dir, "..", "files", "db2uinstance.yaml"), "r") as f:
    mock_get_db2u_instance_cr.return_value = yaml.load(f, Loader=yaml.FullLoader)
  
  mock_db2_pod_exec_db2_get_db_cfg = mocker.patch("mas.devops.db2.db2_pod_exec_db2_get_db_cfg")
  with open(os.path.join(current_dir, "..", "files", "db2getdbcfg.txt"), "r") as f:
    mock_db2_pod_exec_db2_get_db_cfg.return_value = f.read()
  
  mock_db2_pod_exec_db2_get_dbm_cfg = mocker.patch("mas.devops.db2.db2_pod_exec_db2_get_dbm_cfg")
  with open(os.path.join(current_dir, "..", "files", "db2getdbmcfg.txt"), "r") as f:
    mock_db2_pod_exec_db2_get_dbm_cfg.return_value = f.read()
  
  mock_db2_pod_exec_db2set = mocker.patch("mas.devops.db2.db2_pod_exec_db2set")
  with open(os.path.join(current_dir, "..", "files", "db2set.txt"), "r") as f:
      mock_db2_pod_exec_db2set.return_value = f.read()

  mock_ApiClient = mocker.patch("kubernetes.client.api_client.ApiClient")
  mock_k8s_client = mock_ApiClient.return_value

  mas_instance_id = "unittest"
  mas_app_id = "manage"

  with pytest.raises(Exception) as ex:
    db2.validate_db2_config(mock_k8s_client, mas_instance_id, mas_app_id)

  assert ex.value.args[0]["message"] == "3 checks failed"
  assert set(ex.value.args[0]["details"]) == set([
    "[db cfg for BLUDB] APPLHEAPSZ: WRONG != AUTOMATIC(8192)",
    "[dbm cfg] AGENT_STACK_SZ: WRONG != 1024",
    "[registry cfg] DB2AUTH: WRONG != OSAUTHDB,ALLOW_LOCAL_FALLBACK,PLUGIN_AUTO_RELOAD"
  ])
  