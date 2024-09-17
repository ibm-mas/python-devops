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


def test_check_db_cfg_no_dbConfig(mocker):
  mocker.patch("mas.devops.db2.db2_pod_exec_db2_get_db_cfg")
  assert db2.check_db_cfg(dict(name="a"), None, None, None) == []

def test_check_db_cfg_empty_dbConfig(mocker):
  mocker.patch("mas.devops.db2.db2_pod_exec_db2_get_db_cfg")
  assert db2.check_db_cfg(dict(name="a", dbConfig=[]), None, None, None) == []

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


def test_check_dbm_cfg_no_spec():
  db2_instance_cr = dict(
  )
  assert db2.check_dbm_cfg(db2_instance_cr, None, None, None) == []

def test_check_dbm_cfg_no_environment():
  db2_instance_cr = dict(
    spec=dict()
  )
  assert db2.check_dbm_cfg(db2_instance_cr, None, None, None) == []

def test_check_dbm_cfg_no_instance():
  db2_instance_cr = dict(
    spec=dict(
      environment=dict()
    )
  )
  assert db2.check_dbm_cfg(db2_instance_cr, None, None, None) == []

def test_check_dbm_cfg_no_dbmConfig():
  db2_instance_cr = dict(
    spec=dict(
      environment=dict(
        instance=dict()
      )
    )
  )
  assert db2.check_dbm_cfg(db2_instance_cr, None, None, None) == []

def test_check_dbm_cfg_empty_dbmConfig():
  db2_instance_cr = dict(
    spec=dict(
      environment=dict(
        instance=dict(
          dbmConfig=dict()
        )
      )
    )
  )
  assert db2.check_dbm_cfg(db2_instance_cr, None, None, None) == []

def test_check_dbm_cfg(mocker):

  mock_db2_pod_exec_db2_get_dbm_cfg = mocker.patch("mas.devops.db2.db2_pod_exec_db2_get_dbm_cfg")
  mock_db2_pod_exec_db2_get_dbm_cfg.return_value = '''
    Agent stack size                       (AGENT_STACK_SZ) = 1024
  '''

  db2_instance_cr = dict(
    spec=dict(
      environment=dict(
        instance = dict(
          dbmConfig=dict(
            AGENT_STACK_SZ='2048',
            NOTFOUNDINOUTPUT="XXX",
          )
        )
      )
    )
  )

  assert set(db2.check_dbm_cfg(db2_instance_cr, None, None, None)) == set([
    f"[dbm cfg] NOTFOUNDINOUTPUT not found in output of db2 get dbm cfg command",
    f"[dbm cfg] AGENT_STACK_SZ: 2048 != 1024"
  ])




def test_check_reg_cfg_no_spec():
  db2_instance_cr = dict(
  )
  assert db2.check_reg_cfg(db2_instance_cr, None, None, None) == []

def test_check_reg_cfg_no_environment():
  db2_instance_cr = dict(
    spec=dict()
  )
  assert db2.check_reg_cfg(db2_instance_cr, None, None, None) == []

def test_check_reg_cfg_no_instance():
  db2_instance_cr = dict(
    spec=dict(
      environment=dict()
    )
  )
  assert db2.check_reg_cfg(db2_instance_cr, None, None, None) == []

def test_check_reg_cfg_no_registry():
  db2_instance_cr = dict(
    spec=dict(
      environment=dict(
        instance=dict()
      )
    )
  )
  assert db2.check_reg_cfg(db2_instance_cr, None, None, None) == []

def test_check_reg_cfg_empty_registry():
  db2_instance_cr = dict(
    spec=dict(
      environment=dict(
        instance=dict(
          registry=dict()
        )
      )
    )
  )
  assert db2.check_reg_cfg(db2_instance_cr, None, None, None) == []


def test_check_reg_cfg(mocker):

  mock_db2_pod_exec_db2set = mocker.patch("mas.devops.db2.db2_pod_exec_db2set")
  mock_db2_pod_exec_db2set.return_value = '''
    DB2AUTH=OSAUTHDB,ALLOW_LOCAL_FALLBACK,PLUGIN_AUTO_RELOAD
    DB2_FMP_COMM_HEAPSZ=65536 [O]
  '''

  db2_instance_cr = dict(
    spec=dict(
      environment=dict(
        instance = dict(
          registry=dict(
            DB2AUTH='WRONG',
            NOTFOUNDINOUTPUT="XXX",
          )
        )
      )
    )
  )

  assert set(db2.check_reg_cfg(db2_instance_cr, None, None, None)) == set([
    f"[registry cfg] NOTFOUNDINOUTPUT not found in output of db2set command",
    f"[registry cfg] DB2AUTH: WRONG != OSAUTHDB,ALLOW_LOCAL_FALLBACK,PLUGIN_AUTO_RELOAD"
  ])

@pytest.mark.parametrize("test_case_name, expected_failures", [
  # This test case simulates what will happen when we run the validate_db2_config using the IoT Db2uInstance CR
  # as we have it today in fvtsaas after the CR settings have been applied successfully to DB2
  # (there are currently no custom settings set for IoT, so the validate should skip all the checks)
  (
    "iot",[
    ]
  ),

  # This test case simulates what will happen when we run the validate_db2_config using the Manage Db2uInstance CR
  # as we have it today in fvtsaas after the CR settings have been applied successfully to DB2
  (
    "manage_pass",[
    ]
  ),

  # This test case simulates what will happen when we run the validate_db2_config using the Manage Db2uInstance CR
  # as we have it today in fvtsaas against default DB2 configuration values
  ("manage_fail", [
    "[db cfg for BLUDB] APPLHEAPSZ: WRONG != AUTOMATIC(256)",
    "[db cfg for BLUDB] AUTHN_CACHE_DURATION: 10 != 3",
    "[db cfg for BLUDB] AUTHN_CACHE_USERS: 100 != 0",
    "[db cfg for BLUDB] AUTO_REORG: OFF != ON",
    "[db cfg for BLUDB] CATALOGCACHE_SZ: 800 != 742",
    "[db cfg for BLUDB] CHNGPGS_THRESH: 40 != 80",
    "[db cfg for BLUDB] DDL_CONSTRAINT_DEF: YES != NO",
    "[db cfg for BLUDB] LOCKTIMEOUT: 300 != -1",
    "[db cfg for BLUDB] LOGBUFSZ: 1024 != 2152",
    "[db cfg for BLUDB] LOGFILSIZ: 32768 != 50000",
    "[db cfg for BLUDB] LOGPRIMARY: 100 != 20",
    "[db cfg for BLUDB] LOGSECOND: 156 != 30",
    "[db cfg for BLUDB] MIRRORLOGPATH: /mnt/backup != ",
    "[db cfg for BLUDB] NUM_DB_BACKUPS: 60 != 2",
    "[db cfg for BLUDB] REC_HIS_RETENTN: 60 != 0",
    "[db cfg for BLUDB] SHEAPTHRES_SHR: automatic != 1336548",
    "[db cfg for BLUDB] SORTHEAP: automatic != 66827",
    "[db cfg for BLUDB] STMTHEAP: 20000 != AUTOMATIC(16384)",
    "[db cfg for BLUDB] STMT_CONC: LITERALS != OFF",
    "[db cfg for BLUDB] WLM_ADMISSION_CTRL: NO != YES",
    "[dbm cfg] AGENT_STACK_SZ: WRONG != 1024",
    "[dbm cfg] FENCED_POOL: 50 != AUTOMATIC(MAX_COORDAGENTS)",
    "[dbm cfg] KEEPFENCED: NO != YES",
    "[registry cfg] DB2AUTH: WRONG != OSAUTHDB",
    "[registry cfg] DB2_4K_DEVICE_SUPPORT not found in output of db2set command",
    "[registry cfg] DB2_BCKP_PAGE_VERIFICATION not found in output of db2set command",
    "[registry cfg] DB2_CDE_REDUCED_LOGGING not found in output of db2set command",
    "[registry cfg] DB2_EVALUNCOMMITTED not found in output of db2set command",
    "[registry cfg] DB2_FMP_COMM_HEAPSZ not found in output of db2set command",
    "[registry cfg] DB2_FMP_RUN_AS_CONNECTED_USER: NO != YES",
    "[registry cfg] DB2_INLIST_TO_NLJN not found in output of db2set command",
    "[registry cfg] DB2_MINIMIZE_LISTPREFETCH not found in output of db2set command",
    "[registry cfg] DB2_OBJECT_STORAGE_LOCAL_STAGING_PATH: /mnt/backup/staging != /mnt/bludata0/scratch/db2/RemoteStorage",
    "[registry cfg] DB2_SKIPDELETED not found in output of db2set command",
    "[registry cfg] DB2_SKIPINSERTED not found in output of db2set command",
    "[registry cfg] DB2_USE_ALTERNATE_PAGE_CLEANING: ON != ON [DB2_WORKLOAD]",
    "[registry cfg] DB2_WORKLOAD: MAXIMO != ANALYTICS",
  ]),
])

def test_validate_db2_config(test_case_name, expected_failures, mocker):
  '''
  Each test case corresponds to a folder under test/test_cases.
  Each folder must contain a file db2uinstance.yaml and optionally db2getdbcfg.txt, db2getdbmcfg.txt and db2set.txt.
  '''

  current_dir = os.path.dirname(os.path.abspath(__file__))

  mock_get_db2u_instance_cr = mocker.patch("mas.devops.db2.get_db2u_instance_cr")
  with open(os.path.join(current_dir, "..", "test_cases", test_case_name, "db2uinstance.yaml"), "r") as f:
    mock_get_db2u_instance_cr.return_value = yaml.load(f, Loader=yaml.FullLoader)
  
  mock_db2_pod_exec_db2_get_db_cfg = mocker.patch("mas.devops.db2.db2_pod_exec_db2_get_db_cfg")
  try:
    with open(os.path.join(current_dir, "..", "test_cases", test_case_name, "db2getdbcfg.txt"), "r") as f:
      mock_db2_pod_exec_db2_get_db_cfg.return_value = f.read()
  except FileNotFoundError:
    mock_db2_pod_exec_db2_get_db_cfg.return_value = None
    
  mock_db2_pod_exec_db2_get_dbm_cfg = mocker.patch("mas.devops.db2.db2_pod_exec_db2_get_dbm_cfg")
  try:
    with open(os.path.join(current_dir, "..", "test_cases", test_case_name, "db2getdbmcfg.txt"), "r") as f:
      mock_db2_pod_exec_db2_get_dbm_cfg.return_value = f.read()
  except FileNotFoundError:
    mock_db2_pod_exec_db2_get_dbm_cfg.return_value = None
  
  mock_db2_pod_exec_db2set = mocker.patch("mas.devops.db2.db2_pod_exec_db2set")
  try:
    with open(os.path.join(current_dir, "..", "test_cases", test_case_name, "db2set.txt"), "r") as f:
        mock_db2_pod_exec_db2set.return_value = f.read()
  except FileNotFoundError:
    mock_db2_pod_exec_db2set.return_value = None
  
  mock_ApiClient = mocker.patch("kubernetes.client.api_client.ApiClient")
  mock_k8s_client = mock_ApiClient.return_value

  mas_instance_id = "unittest"
  mas_app_id = test_case_name

  if len(expected_failures) == 0:
    db2.validate_db2_config(mock_k8s_client, mas_instance_id, mas_app_id)
  else:
    with pytest.raises(Exception) as ex:
      db2.validate_db2_config(mock_k8s_client, mas_instance_id, mas_app_id)

    assert ex.value.args[0]["message"] == f"{len(expected_failures)} checks failed"
    assert set(ex.value.args[0]["details"]) == set(expected_failures)
    