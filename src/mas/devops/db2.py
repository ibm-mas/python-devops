# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

import yaml
import re
from kubernetes import client, config
from .ocp import execInPod




def get_db2u_instance_cr(custom_objects_api: client.CustomObjectsApi, mas_instance_id: str, mas_app_id: str) -> dict:
  return custom_objects_api.get_namespaced_custom_object(
    group="db2u.databases.ibm.com", 
    version="v1", 
    namespace=f"db2u-{mas_instance_id}", 
    plural="db2uinstances", 
    name=f"db2wh-{mas_instance_id}-{mas_app_id}"
  )

  # db2u_instance_cr_path = "./files/db2uinstance.yaml"
  # with open(db2u_instance_cr_path, "r") as f:
  #   return yaml.load(f, Loader=yaml.FullLoader)



def db2_pod_exec(core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str, command: list) -> str:
  pod_name = f"c-db2wh-{mas_instance_id}-{mas_app_id}-db2u-0"
  namespace = f"db2u-{mas_instance_id}"
  return execInPod(core_v1_api, pod_name, namespace, command)


def db2_pod_exec_db2_get_db_cfg(core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str, db_name: str) -> str:
  command = ["su", "-lc", f"db2 get db cfg for {db_name}", "db2inst1"]
  return db2_pod_exec(core_v1_api, mas_instance_id, mas_app_id, command)
  # with open("./files/db2getdbcfg.txt", "r") as f:
  #   return f.read()

def db2_pod_exec_db2_get_dbm_cfg(core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str) -> str:
  command = ["su", "-lc", f"db2 get dbm cfg", "db2inst1"]
  return db2_pod_exec(core_v1_api, mas_instance_id, mas_app_id, command)

def db2_pod_exec_db2set(core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str) -> str:
  command = ["su", "-lc", f"db2set", "db2inst1"]
  return db2_pod_exec(core_v1_api, mas_instance_id, mas_app_id, command)


def cr_pod_v_matches(cr_k: str, cr_v: str, pod_v: str) -> bool:
  # special cases where cr_v and pod_v values are expressed differently even if they mean the same thing
  if cr_k in ["MIRRORLOGPATH"]:
    # db2 appends something like "/NODE0000/LOGSTREAM0000/" to the cr_v in these cases
   return pod_v.startswith(cr_v)
  
  # Look for e.g. 8192 AUTOMATIC -> AUTOMATIC(8192)
  matches = re.search(r"(\d+)\s*AUTOMATIC", cr_v, re.IGNORECASE)
  if matches is not None:
    cr_v_num = int(matches.group(1))
    return pod_v == f"AUTOMATIC({cr_v_num})"
  
  # Look for e.g. AUTOMATIC -> AUTOMATIC(6554)
  if cr_v.upper() == "AUTOMATIC":
    return re.search(r"AUTOMATIC\(\d+\)", pod_v) is not None
  
  return pod_v == cr_v


def check_db_cfgs(db2u_instance_cr, core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str) -> list:
  failures = []

  db2u_instance_cr_databases = db2u_instance_cr.get("spec", {}).get("environment", {}).get("databases", {})
  if len(db2u_instance_cr_databases) == 0:
    raise Exception("spec.environment.databases not found or empty")

  # Check each db cfg
  for db in db2u_instance_cr_databases:
    db_name = db["name"]
    db_cfg_pod = db2_pod_exec_db2_get_db_cfg(core_v1_api, mas_instance_id, mas_app_id, db_name)
    print(f"- Checking db cfg for {db_name}")
    print("----------------------------------")
    print(db_cfg_pod)
    print()
    db_cfg_cr = db['dbConfig']
    if db_cfg_cr is None or len(db_cfg_cr) == 0:
      print(f"[{db_name}] No dbConfig found in CR, skipping validation for this database")
      continue

    for cr_k, cr_v in db_cfg_cr.items():
      matches =  re.search(fr"\({cr_k}\)\s=\s(.*)$", db_cfg_pod, re.MULTILINE)
      if matches is None:
        failures.append(f"[{db_name}] CR dbConfig key {cr_k} not found in output of db2 get db cfg command")
        continue
      pod_v = matches.group(1)
      print(f"[{db_name}] Checking if {cr_k}: {cr_v} == {pod_v}")

      if not cr_pod_v_matches(cr_k, cr_v, pod_v):
        failures.append(f"[{db_name}] {cr_k}: {cr_v} != {pod_v}")
  
  return failures
        
def check_dbm_cfg(db2u_instance_cr, core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str) -> list:
  failures = []

  # Check dbm config
  print(f"- Checking dbm cfg")
  print("----------------------------------")
  dbm_cfg_cr = db2u_instance_cr.get("spec", {}).get("environment", {}).get("instance", {}).get("dbmConfig", {})
  if len(dbm_cfg_cr) == 0:
    print("spec.environment.instance.dbmConfig not found or empty, skipping validation")
    return failures

  dbm_cfg_pod = db2_pod_exec_db2_get_dbm_cfg(core_v1_api, mas_instance_id, mas_app_id)
  print(dbm_cfg_pod)
  print()
  for cr_k, cr_v in dbm_cfg_cr.items():
    matches =  re.search(fr"\({cr_k}\)\s=\s(.*)$", dbm_cfg_pod, re.MULTILINE)
    if matches is None:
      failures.append(f"CR dbmConfig key {cr_k} not found in output of db2 get dbm cfg command")
      continue
    pod_v = matches.group(1)
    print(f"Checking if {cr_k}: {cr_v} == {pod_v}")

    if not cr_pod_v_matches(cr_k, cr_v, pod_v):
      failures.append(f"{cr_k}: {cr_v} != {pod_v}")

  return failures

def check_reg_cfg(db2u_instance_cr, core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str) -> list:
  failures = []

  # Check registry cfg
  print()
  print(f"- Checking registry cfg")
  print("----------------------------------")

  reg_cfg_cr = db2u_instance_cr.get("spec", {}).get("environment", {}).get("instance", {}).get("registry", {})
  if len(reg_cfg_cr) == 0:
    print("spec.environment.instance.registry not found or empty, skipping validation")
    return failures

  reg_cfg_pod = db2_pod_exec_db2set(core_v1_api, mas_instance_id, mas_app_id)
  print(reg_cfg_pod)

  for cr_k, cr_v in reg_cfg_cr.items():
    # regex ignores any trailing [O] (which indicates the param has been overridden I think)
    matches =  re.search(fr"{cr_k}=(.*?)(?:\s\[O\])?$", reg_cfg_pod, re.MULTILINE)
    if matches is None:
      failures.append(f"CR registry config key {cr_k} not found in output of db2set command")
      continue
    pod_v = matches.group(1)
    print(f"Checking if {cr_k}: {cr_v} == {pod_v}")

    if not cr_pod_v_matches(cr_k, cr_v, pod_v):
      failures.append(f"{cr_k}: {cr_v} != {pod_v}")

  return failures


def validate_db2_config(k8s_client: client.api_client.ApiClient, mas_instance_id: str, mas_app_id: str):

  core_v1_api = client.CoreV1Api(k8s_client)
  custom_objects_api = client.CustomObjectsApi(k8s_client)

  db2u_instance_cr = get_db2u_instance_cr(custom_objects_api, mas_instance_id, mas_app_id)
  db_failures = check_db_cfgs(db2u_instance_cr, core_v1_api, mas_instance_id, mas_app_id)
  dbm_failures = check_dbm_cfg(db2u_instance_cr, core_v1_api, mas_instance_id, mas_app_id)
  reg_failures = check_reg_cfg(db2u_instance_cr, core_v1_api, mas_instance_id, mas_app_id)

  all_failures = [*db_failures, *dbm_failures, *reg_failures]

  if len(all_failures) > 0:
    print()
    print("FAILURES:")
    for f in all_failures:
      print(f)

  if len(all_failures) > 0:
    raise Exception(f"Property mismatches found: {all_failures}")
  