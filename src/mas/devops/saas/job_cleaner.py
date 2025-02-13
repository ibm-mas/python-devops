# *****************************************************************************
# Copyright (c) 2025 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from kubernetes import client
import logging

logger = logging.getLogger(__name__)


def cleanup_jobs(k8s_client: client.api_client.ApiClient, label: str):
    core_v1_api = client.CoreV1Api(k8s_client)
    batch_v1_api = client.BatchV1Api(k8s_client)

    cms = core_v1_api.list_config_map_for_all_namespaces(label_selector=label)

    for cm in cms.items:
        cm_ns = cm.metadata.namespace
        job_cleanup_group = cm.metadata.labels[label]
        logger.info("")
        logger.info(f"{job_cleanup_group} in {cm_ns}")
        logger.info("-------------------------------")
        try:
            current_job_name = cm.data['current_job_name']
            logger.info(f"Current Job Name: {current_job_name}")

            # get all Jobs in the same namespace as the configmap that have LABEL: job_cleanup_group
            jobs_in_cleanup_group = batch_v1_api.list_namespaced_job(cm_ns, label_selector=f"{label}={job_cleanup_group}")

            for job in jobs_in_cleanup_group.items:
                job_name = job.metadata.name
                if job_name != current_job_name:
                    logger.info(f"Deleting old Job resource: {job_name}")

        except Exception as e:
            logger.error(f"Skipping {job_cleanup_group} in {cm_ns}: {repr(e)}")
