# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************


import re
from kubernetes import client
from .ocp import execInPod
import logging
import yaml

H1_BREAK = "================================================================"
H2_BREAK = "----------------------------------------------------------------"

logger = logging.getLogger(__name__)


def get_db2u_instance_cr(custom_objects_api: client.CustomObjectsApi, mas_instance_id: str, mas_app_id: str) -> dict:
    cr_name = f"db2wh-{mas_instance_id}-{mas_app_id}"
    namespace = f"db2u-{mas_instance_id}"
    logger.debug(f"Getting Db2uInstance CR {cr_name} in {namespace}")

    db2u_instance_cr = custom_objects_api.get_namespaced_custom_object(
        group="db2u.databases.ibm.com",
        version="v1",
        namespace=namespace,
        plural="db2uinstances",
        name=cr_name
    )

    return db2u_instance_cr


def db2_pod_exec(core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str, command: list) -> str:
    pod_name = f"c-db2wh-{mas_instance_id}-{mas_app_id}-db2u-0"
    namespace = f"db2u-{mas_instance_id}"
    return execInPod(core_v1_api, pod_name, namespace, command)


def db2_pod_exec_db2_get_db_cfg(core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str, db_name: str) -> str:
    command = ["su", "-lc", f"db2 get db cfg for {db_name}", "db2inst1"]
    return db2_pod_exec(core_v1_api, mas_instance_id, mas_app_id, command)


def db2_pod_exec_db2_get_dbm_cfg(core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str) -> str:
    command = ["su", "-lc", "db2 get dbm cfg", "db2inst1"]
    return db2_pod_exec(core_v1_api, mas_instance_id, mas_app_id, command)


def db2_pod_exec_db2set(core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str) -> str:
    command = ["su", "-lc", "db2set", "db2inst1"]
    return db2_pod_exec(core_v1_api, mas_instance_id, mas_app_id, command)


def cr_pod_v_matches(cr_k: str, cr_v: str, pod_v: str) -> bool:

    logger.debug(f"[{cr_k}] '{cr_v}' ~= '{pod_v}'")
    # special cases where cr_v and pod_v values are expressed differently even if they mean the same thing
    if cr_k in ["MIRRORLOGPATH"]:
        # db2 appends something like "/NODE0000/LOGSTREAM0000/" to the cr_v in these cases
        return pod_v.startswith(cr_v)

    # Look for e.g. 8192 AUTOMATIC -> AUTOMATIC(8192)
    matches = re.search(r"(\d+)\s*AUTOMATIC", cr_v, re.IGNORECASE)
    if matches is not None:
        cr_v_num = int(matches.group(1))
        return pod_v == f"AUTOMATIC({cr_v_num})"

    # Look for e.g. AUTOMATIC -> AUTOMATIC(6554) or AUTOMATIC
    if cr_v.upper() == "AUTOMATIC":
        return pod_v == "AUTOMATIC" or re.search(r"AUTOMATIC\(\d+\)", pod_v) is not None

    return pod_v == cr_v


def check_db_cfgs(db2u_instance_cr: dict, core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str) -> list:
    """
    Runs check_db_cfg for each database in the provided Db2uInstance CR

    Parameters:
      db2u_instance_cr (dict): the Db2uInstanceCR as a dict (use get_db2u_instance_cr)
      core_v1_api (client.CoreV1Api): The Kubernetes API client
      mas_instance_id (str): The ID of the MAS instance.
      mas_app_id (str): The ID of the MAS app the DB2 database is for (e.g. "manage", "iot")

    Returns:
      list: The outputs of each call to check_db_cfg concatenated together
    """
    failures = []

    db2u_instance_cr_databases = db2u_instance_cr.get("spec", {}).get("environment", {}).get("databases", {})
    if len(db2u_instance_cr_databases) == 0:
        raise Exception("spec.environment.databases not found or empty")

    # Check each db cfg
    for cr_db in db2u_instance_cr_databases:
        failures = [*failures, *check_db_cfg(cr_db, core_v1_api, mas_instance_id, mas_app_id)]

    return failures


def check_db_cfg(db_dr: dict, core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str) -> list:
    """
    Check that the parameters in the provided db dict taken from the Db2uInstance CR align with those in the output of the
    db2 get db cfg command (i.e. the configuration that is actually active in DB2).

    Parameters:
      db_dr (dict): one element under spec.environment.databases taken from the Db2uInstance CR
      core_v1_api (client.CoreV1Api): The Kubernetes API client
      mas_instance_id (str): The ID of the MAS instance.
      mas_app_id (str): The ID of the MAS app the DB2 database is for (e.g. "manage", "iot")

    Returns:
      list: A list of strings describing any mismatches found between the CR and active DB2 configuration.
            Any empty list implies all configuration matches.
    """
    failures = []

    db_name = db_dr["name"]
    db_cfg_pod = db2_pod_exec_db2_get_db_cfg(core_v1_api, mas_instance_id, mas_app_id, db_name)

    logger.info(f"Checking db cfg for {db_name}\n{H1_BREAK}")

    db_cfg_cr = db_dr.get('dbConfig', None)
    if db_cfg_cr is None or len(db_cfg_cr) == 0:
        logger.info(f"No dbConfig for db {db_name} found in CR, skipping db cfg checks for {db_name}\n")
        return []

    logger.debug(f"db2 db {db_name} cfg output:\n{H2_BREAK}{db_cfg_pod}{H2_BREAK}")
    logger.debug(f"db2 db {db_name} cr settings:\n{H2_BREAK}\n{yaml.dump(db_cfg_cr, sort_keys=False, default_flow_style=False)}{H2_BREAK}")

    logger.debug(f"Running checks\n{H2_BREAK}")
    for cr_k, cr_v in db_cfg_cr.items():
        matches = re.search(fr"\({cr_k}\)\s=\s(.*)$", db_cfg_pod, re.MULTILINE)
        if matches is None:
            failures.append(f"[db cfg for {db_name}] {cr_k} not found in output of db2 get db cfg command")
            continue
        pod_v = matches.group(1)

        if not cr_pod_v_matches(cr_k, cr_v, pod_v):
            failures.append(f"[db cfg for {db_name}] {cr_k}: {cr_v} != {pod_v}")
    logger.debug(f"\n{H2_BREAK}")

    if len(failures) > 0:
        logger.warning(f"{len(failures)} checks failed for db cfg {db_name}\n")
    else:
        logger.info(f"All db cfg checks for {db_name} passed\n")
    return failures


def check_dbm_cfg(db2u_instance_cr: dict, core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str) -> list:
    """
    Check that the database manager (dbmConfig) parameters from the Db2uInstance CR align with those in the output of the
    db2 get dbm cfg command (i.e. the configuration that is actually active in DB2).

    Parameters:
      db2u_instance_cr (dict): the Db2uInstanceCR as a dict (use get_db2u_instance_cr)
      core_v1_api (client.CoreV1Api): The Kubernetes API client
      mas_instance_id (str): The ID of the MAS instance.
      mas_app_id (str): The ID of the MAS app the DB2 database is for (e.g. "manage", "iot")

    Returns:
      list: A list of strings describing any mismatches found between the CR and active DB2 configuration.
            Any empty list implies all configuration matches.
    """
    failures = []

    # Check dbm config
    logger.info(f"Checking dbm cfg\n{H1_BREAK}")
    dbm_cfg_cr = db2u_instance_cr.get("spec", {}).get("environment", {}).get("instance", {}).get("dbmConfig", {})
    if len(dbm_cfg_cr) == 0:
        logger.info("spec.environment.instance.dbmConfig not found or empty, skipping dbm cfg checks\n")
        return []

    dbm_cfg_pod = db2_pod_exec_db2_get_dbm_cfg(core_v1_api, mas_instance_id, mas_app_id)

    logger.debug(f"db2 dbm cfg output:\n{H2_BREAK}{dbm_cfg_pod}{H2_BREAK}")
    logger.debug(f"db2 dbm cr settings:\n{H2_BREAK}\n{yaml.dump(dbm_cfg_cr, sort_keys=False, default_flow_style=False)}{H2_BREAK}")

    logger.debug(f"Running checks\n{H2_BREAK}")
    for cr_k, cr_v in dbm_cfg_cr.items():
        matches = re.search(fr"\({cr_k}\)\s=\s(.*)$", dbm_cfg_pod, re.MULTILINE)
        if matches is None:
            failures.append(f"[dbm cfg] {cr_k} not found in output of db2 get dbm cfg command")
            continue
        pod_v = matches.group(1)

        if not cr_pod_v_matches(cr_k, cr_v, pod_v):
            failures.append(f"[dbm cfg] {cr_k}: {cr_v} != {pod_v}")
    logger.debug(f"\n{H2_BREAK}")

    if len(failures) > 0:
        logger.warning(f"{len(failures)} checks failed for dbm cfg\n")
    else:
        logger.info("All dbm cfg checks passed\n")

    return failures


def check_reg_cfg(db2u_instance_cr: dict, core_v1_api: client.CoreV1Api, mas_instance_id: str, mas_app_id: str) -> list:
    """
    Check that the registry parameters from the Db2uInstance CR align with those in the output of the
    db2set command (i.e. the configuration that is actually active in DB2).

    Parameters:
      db2u_instance_cr (dict): the Db2uInstanceCR as a dict (use get_db2u_instance_cr)
      core_v1_api (client.CoreV1Api): The Kubernetes API client
      mas_instance_id (str): The ID of the MAS instance.
      mas_app_id (str): The ID of the MAS app the DB2 database is for (e.g. "manage", "iot")

    Returns:
      list: A list of strings describing any mismatches found between the CR and active DB2 configuration.
            Any empty list implies all configuration matches.
    """
    failures = []

    # Check registry cfg
    logger.info(f"Checking registry cfg\n{H1_BREAK}")

    reg_cfg_cr = db2u_instance_cr.get("spec", {}).get("environment", {}).get("instance", {}).get("registry", {})
    if len(reg_cfg_cr) == 0:
        logger.info("spec.environment.instance.registry not found or empty, skipping registry cfg checks\n")
        return []

    reg_cfg_pod = db2_pod_exec_db2set(core_v1_api, mas_instance_id, mas_app_id)

    logger.debug(f"db2set output:\n{H2_BREAK}{reg_cfg_pod}{H2_BREAK}")
    logger.debug(f"db2 cr registry settings:\n{H2_BREAK}\n{yaml.dump(reg_cfg_cr, sort_keys=False, default_flow_style=False)}{H2_BREAK}")

    logger.debug(f"Running checks\n{H2_BREAK}")
    for cr_k, cr_v in reg_cfg_cr.items():
        # regex ignores any trailing [O] (which indicates the param has been overridden I think)
        matches = re.search(fr"{cr_k}=(.*?)(?:\s\[O\])?$", reg_cfg_pod, re.MULTILINE)
        if matches is None:
            failures.append(f"[registry cfg] {cr_k} not found in output of db2set command")
            continue
        pod_v = matches.group(1)

        if not cr_pod_v_matches(cr_k, cr_v, pod_v):
            failures.append(f"[registry cfg] {cr_k}: {cr_v} != {pod_v}")
    logger.debug(f"\n{H2_BREAK}")

    if len(failures) > 0:
        logger.warning(f"{len(failures)} registry cfg checks failed\n")
    else:
        logger.info("All registry cfg checks passed\n")

    return failures


def validate_db2_config(k8s_client: client.api_client.ApiClient, mas_instance_id: str, mas_app_id: str):

    core_v1_api = client.CoreV1Api(k8s_client)
    custom_objects_api = client.CustomObjectsApi(k8s_client)

    db2u_instance_cr = get_db2u_instance_cr(custom_objects_api, mas_instance_id, mas_app_id)
    db_failures = check_db_cfgs(db2u_instance_cr, core_v1_api, mas_instance_id, mas_app_id)
    dbm_failures = check_dbm_cfg(db2u_instance_cr, core_v1_api, mas_instance_id, mas_app_id)
    reg_failures = check_reg_cfg(db2u_instance_cr, core_v1_api, mas_instance_id, mas_app_id)

    all_failures = [*db_failures, *dbm_failures, *reg_failures]

    logger.info(f"Results\n{H1_BREAK}")
    if len(all_failures) > 0:

        logger.error(f"{len(all_failures)} checks failed:")

        logger.error(f" {len(db_failures)} db cfg failures:")
        for db_failure in db_failures:
            logger.error(f"    {db_failure}")

        logger.error(f" {len(dbm_failures)} dbm cfg failures:")
        for dbm_failure in dbm_failures:
            logger.error(f"    {dbm_failure}")

        logger.error(f" {len(reg_failures)} registry cfg failures:")
        for reg_failure in reg_failures:
            logger.error(f"    {reg_failure}")

        logger.info("Raising exception:")
        raise Exception(dict(
            message=f"{len(all_failures)} checks failed",
            details=all_failures
        ))
    else:
        logger.info("All checks passed")
