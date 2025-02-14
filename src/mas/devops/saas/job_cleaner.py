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

logger = logging.getLogger(__name__)

# TODO: dry-run mode that just logs (does not delete anything)


# TODO: test case: four jobs with same cleanup_group id but different namespaces


def job_details(job, label):
    name = job.metadata.name
    namespace = job.metadata.namespace
    creation_timestamp = job.metadata.creation_timestamp
    cleanup_group = job.metadata.labels[label]

    return f"{name} {namespace} {cleanup_group} {creation_timestamp}"


def cleanup_jobs(k8s_client: client.api_client.ApiClient, label: str, limit: int = 100):
    batch_v1_api = client.BatchV1Api(k8s_client)

    # we need to be sure we have all Jobs loaded up front (we can't do the cleanup page by page)
    # so a page boundary may cut a cleanup_group in half, which would cause inconsistent behaviour

    # set of tuples (namespace, cleanup_group_id)
    cleanup_groups = set()
    _continue = None
    while True:

        # to avoid loading all jobs into memory at once (there may be a LOT),
        # do an initial query to look for all unique group_ids in the cluster
        # later, for each group_id, another query to find all jobs belonging to that group
        # We're trading cpu time / network io for memory here..

        jobs_page = batch_v1_api.list_job_for_all_namespaces(
            label_selector=label,
            limit=limit,
            _continue=_continue
        )
        _continue = jobs_page.metadata._continue

        for job in jobs_page.items:
            cleanup_groups.add((job.metadata.namespace, job.metadata.labels[label]))

        if _continue is None:
            break

    # NOTE: it's possible for things to change in the cluster while this process is ongoing
    # e.g.:
    #  - a new sync cycle creates a newer version of Job; not a problem, just means an orphaned job will stick around for one extra cycle
    #  - a new cleanup group appears; not a problem, the new cleanup group will be handled in the next cycle
    #  - ... other race conditions?
    # this process is eventually consistent

    # Now we know all the cleanup group ids in the cluster
    # we can deal with each one separately; we only have to load the job resources for that particular group into memory at once
    # (we have to load into memory in order to guarantee the jobs are sorted by creation_date
    # if we could (can?) rely on K8S to always return them in this order then we could evaluate each page of Jobs lazily
    for (namespace, cleanup_group_id) in cleanup_groups:

        print()
        print()
        print(f"{namespace} / {cleanup_group_id}")
        print("============================")

        # page through all jobs in this namespace and group, and chain together all the resulting iterators
        job_items_iters = []
        while True:
            jobs_page = batch_v1_api.list_namespaced_job(
                namespace,
                label_selector=f"{label}={cleanup_group_id}",
                limit=limit,
                _continue=_continue
            )
            job_items_iters.append(jobs_page.items)
            _continue = jobs_page.metadata._continue
            if _continue is None:
                break

        jobs = itertools.chain(*job_items_iters)

        # sort the jobs by creation_timestamp
        jobs_sorted = iter(sorted(
            jobs,
            key=lambda group_job: group_job.metadata.creation_timestamp,
            reverse=True
        ))

        # inspect the first Job - i.e. the one created most recently
        # whatever happens we definitely will not be deleting this job (in this cycle, at least)
        most_recent_job = next(jobs_sorted)
        print()
        print("Most recent Job")
        print("------")
        print(job_details(most_recent_job, label))

        # TODO: prune prior jobs even if most recent job has failed?
        #       or leave them be as they may provide valuable debugging info?

        print()
        print("Old Jobs to be pruned")
        print("------")
        for job in jobs_sorted:
            # prune prior jobs even if most recent job has failed?
            # or leave them be as they may provide valuable debugging info?
            print(job_details(job, label))
