# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
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
        logger.info(f"{job_cleanup_group} in {cm_ns}")
        try:
            current_job_name = cm.data['current_job_name']

            # get all Jobs in the same namespace as the configmap that have LABEL: job_cleanup_group
            jobs_in_cleanup_group = batch_v1_api.list_namespaced_job(cm_ns, label_selector=f"{label}={job_cleanup_group}")

            # sanity checks, abort cleanup of this group if any of these fail
            #   - one of the jobs should be named current_job_name
            #   - all jobs names should have job_cleanup_group as a prefix
            found_current_job = False
            for job in jobs_in_cleanup_group.items:
                job_name = job.metadata.name

                if job_name == current_job_name:
                    found_current_job = True

                if not job_name.startswith(job_cleanup_group):
                    raise Exception(f"Job name {job_name} has unexpected prefix")

            if found_current_job:
                logger.info(f"   Found current Job resource: {current_job_name}")
            else:
                raise Exception(f"Could not find current job {current_job_name}")

            for job in jobs_in_cleanup_group.items:
                job_name = job.metadata.name
                if job_name != current_job_name:
                    logger.info(f"   Deleting old Job resource: {job_name}")

        except Exception as e:
            logger.error(f"Skipping {job_cleanup_group} in {cm_ns}: {repr(e)}")
