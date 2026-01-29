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
import itertools

# Possible future features: behaviours that diverge from default ArgoCD behaviour (if auto_delete: true were set), but may be useful?:
#       - support option to only purge jobs >n iterations old
#       - avoid purging jobs that are still running
#       - save details / logs from purged jobs (where? to a PV?)


class JobCleaner:
    """
    Kubernetes Job cleanup utility for managing ArgoCD-style job retention.

    This class provides functionality to clean up old Kubernetes Job resources while
    retaining the most recent job in each cleanup group. Jobs are grouped by a label
    and only the newest job (by creation timestamp) in each group is preserved.

    This is useful for ArgoCD applications where auto_delete is not enabled but you
    still want to prevent job accumulation.

    Attributes:
        k8s_client (client.api_client.ApiClient): Kubernetes API client.
        batch_v1_api (client.BatchV1Api): Kubernetes Batch V1 API interface.
        logger (logging.Logger): Logger instance for this class.
    """

    def __init__(self, k8s_client: client.api_client.ApiClient):
        """
        Initialize the JobCleaner with a Kubernetes API client.

        Args:
            k8s_client (client.api_client.ApiClient): Kubernetes API client for cluster operations.
        """
        self.k8s_client = k8s_client
        self.batch_v1_api = client.BatchV1Api(self.k8s_client)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def _get_all_cleanup_groups(self, label: str, limit: int):
        """
        Retrieve all unique cleanup groups across all namespaces.

        This internal method queries all jobs with the specified label and extracts
        unique (namespace, group_id) pairs for processing.

        Args:
            label (str): The label key used to identify and group jobs.
            limit (int): Maximum number of jobs to retrieve per API call (pagination).

        Returns:
            set: Set of tuples containing (namespace, cleanup_group_id) pairs.

        Note:
            This method pages through all jobs to avoid loading everything into memory at once.
        """
        # set of tuples (namespace, cleanup_group_id)
        cleanup_groups = set()
        _continue = None
        while True:

            jobs_page = self.batch_v1_api.list_job_for_all_namespaces(
                label_selector=label,
                limit=limit,
                _continue=_continue
            )
            _continue = jobs_page.metadata._continue

            for job in jobs_page.items:
                cleanup_groups.add((job.metadata.namespace, job.metadata.labels[label]))

            if _continue is None:
                return cleanup_groups

    def _get_all_jobs(self, namespace: str, group_id: str, label: str, limit: int):
        """
        Retrieve all jobs for a specific cleanup group in a namespace.

        This internal method pages through all jobs matching the group ID and chains
        the results together for efficient iteration.

        Args:
            namespace (str): The Kubernetes namespace to query.
            group_id (str): The cleanup group identifier from the label value.
            label (str): The label key used to filter jobs.
            limit (int): Maximum number of jobs to retrieve per API call (pagination).

        Returns:
            itertools.chain: Chained iterator of job items across all pages.

        Note:
            Jobs are not loaded entirely into memory; iterators are chained for efficiency.
        """
        # page through all jobs in this namespace and group, and chain together all the resulting iterators
        job_items_iters = []
        _continue = None
        while True:
            jobs_page = self.batch_v1_api.list_namespaced_job(
                namespace,
                label_selector=f"{label}={group_id}",
                limit=limit,
                _continue=_continue
            )
            job_items_iters.append(jobs_page.items)
            _continue = jobs_page.metadata._continue
            if _continue is None:
                return itertools.chain(*job_items_iters)

    def cleanup_jobs(self, label: str, limit: int, dry_run: bool):
        """
        Clean up old Kubernetes Jobs, retaining only the newest in each group.

        This method identifies all cleanup groups (by label), then for each group,
        sorts jobs by creation timestamp and deletes all except the most recent one.
        The cleanup process is eventually consistent and handles race conditions gracefully.

        Args:
            label (str): The label key used to identify and group jobs (e.g., "argocd.argoproj.io/instance").
            limit (int): Maximum number of jobs to retrieve per API call for pagination.
            dry_run (bool): If True, simulate the cleanup without actually deleting jobs.

        Returns:
            None

        Note:
            - Only the newest job in each group is retained
            - Deletion uses "Foreground" propagation policy
            - The process is eventually consistent; race conditions are handled gracefully
            - Progress is logged for each cleanup group
        """
        dry_run_param = None
        if dry_run:
            dry_run_param = "All"

        # We want to avoid loading all Jobs into memory at once (there may be a lot)
        # We cannot lazily page through Job resources in case a page boundary lands half way through a group
        # Instead, we'll trade cpu time / network IO to save memory by:
        #  - Performing an initial query to load all unique (namespace, group IDs) into memory

        cleanup_groups = self._get_all_cleanup_groups(label, limit)

        self.logger.info(f"Found {len(cleanup_groups)} unique (namespace, cleanup group ID) pairs, processing ...")

        # NOTE: it's possible for things to change in the cluster while this process is ongoing
        # e.g.:
        #  - a new sync cycle creates a newer version of Job; not a problem, just means an orphaned job will stick around for one extra cycle
        #  - a new cleanup group appears; not a problem, the new cleanup group will be handled in the next cycle
        #  - ... other race conditions?
        # this process is eventually consistent

        # Now we know all the cleanup group ids in the cluster
        # we can deal with each one separately; we only have to load the job resources for that particular group into memory at once
        # (we have to load into memory in order to guarantee the jobs are sorted by creation_date)
        i = 0
        for (namespace, group_id) in cleanup_groups:

            self.logger.info("")
            self.logger.info(f"{i}) {group_id} {namespace}")

            jobs = self._get_all_jobs(namespace, group_id, label, limit)

            # sort the jobs by creation_timestamp
            jobs_sorted = sorted(
                jobs,
                key=lambda group_job: group_job.metadata.creation_timestamp,
                reverse=True
            )

            if len(jobs_sorted) == 0:
                self.logger.warning("No Jobs found in group, must have been deleted by some other process, skipping")
                continue
            else:
                first = True
                for job in jobs_sorted:
                    name = job.metadata.name
                    creation_timestamp = str(job.metadata.creation_timestamp)
                    if first:
                        self.logger.info("{0:<6} {1:<65} {2:<65}".format("SKIP", name, creation_timestamp))
                        first = False
                    else:
                        try:
                            self.batch_v1_api.delete_namespaced_job(name, namespace, dry_run=dry_run_param, propagation_policy="Foreground")
                            result = "SUCCESS"
                        except client.rest.ApiException as e:
                            result = f"FAILED: {e}"

                        self.logger.info("{0:<6} {1:<65} {2:<65} {3}".format("PURGE", name, creation_timestamp, result))

            i = i + 1
