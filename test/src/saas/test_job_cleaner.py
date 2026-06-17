# *****************************************************************************
# Copyright (c) 2025 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************
from unittest.mock import patch, Mock, call
from mas.devops.saas.job_cleaner import JobCleaner


def mock_job(name, namespace, labels, creation_timestamp):

    mock = Mock()
    mock.metadata = Mock()
    mock.metadata.name = name
    mock.metadata.namespace = namespace
    mock.metadata.labels = labels
    mock.metadata.creation_timestamp = creation_timestamp

    return mock


jobs_in_cluster = [
    mock_job("job-xa-1", "x", {"mas.ibm.com/job-cleanup-group": "a"}, 1),
    mock_job("job-xa-2", "x", {"mas.ibm.com/job-cleanup-group": "a"}, 2),
    mock_job("job-xa-3", "x", {"mas.ibm.com/job-cleanup-group": "a"}, 3),
    mock_job("job-xb-1", "x", {"mas.ibm.com/job-cleanup-group": "b"}, 1),
    mock_job("job-xb-2", "x", {"mas.ibm.com/job-cleanup-group": "b"}, 2),
    mock_job("job-xc-1", "x", {"mas.ibm.com/job-cleanup-group": "c"}, 2),
    mock_job("job-ya-2", "y", {"mas.ibm.com/job-cleanup-group": "a"}, 2),
    mock_job("job-ya-1", "y", {"mas.ibm.com/job-cleanup-group": "a"}, 1),
    mock_job("job-yothera-1", "y", {"otherlabel": "a"}, 1),
    mock_job("job-zothera-1", "z", {"otherlabel": "a"}, 1),
]


def list_jobs(namespace, label_selector, limit, _continue):
    if _continue is None:
        _continue = 0

    label_selector_kv = label_selector.split("=")

    def filter_func(job):
        if not label_selector_kv[0] in job.metadata.labels:
            return False
        if len(label_selector_kv) == 2 and not job.metadata.labels[label_selector_kv[0]] == label_selector_kv[1]:
            return False
        if namespace is not None and job.metadata.namespace != namespace:
            return False
        return True

    filtered_jobs = list(filter(filter_func, jobs_in_cluster))

    jobs_page = filtered_jobs[_continue : _continue + limit]

    if len(jobs_page) == 0:
        _continue = None
    else:
        _continue = _continue + limit

    return Mock(items=jobs_page, metadata=Mock(_continue=_continue))


def list_job_for_all_namespaces(label_selector, limit, _continue):
    return list_jobs(None, label_selector, limit, _continue)


def list_namespaced_job(namespace, label_selector, limit, _continue):
    return list_jobs(namespace, label_selector, limit, _continue)


@patch("kubernetes.client.BatchV1Api")
def test_get_all_cleanup_groups(mock_batch_v1_api):
    mock_batch_v1_api.return_value.list_job_for_all_namespaces.side_effect = list_job_for_all_namespaces
    jc = JobCleaner(None)
    for limit in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
        assert jc._get_all_cleanup_groups("mas.ibm.com/job-cleanup-group", limit) == {
            ("x", "a"),
            ("x", "b"),
            ("x", "c"),
            ("y", "a"),
        }


@patch("kubernetes.client.BatchV1Api")
def test_get_all_jobs(mock_batch_v1_api):
    mock_batch_v1_api.return_value.list_namespaced_job.side_effect = list_namespaced_job
    jc = JobCleaner(None)
    for limit in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
        assert list(
            map(
                lambda job: job.metadata.name,
                jc._get_all_jobs("x", "a", "mas.ibm.com/job-cleanup-group", limit),
            )
        ) == ["job-xa-1", "job-xa-2", "job-xa-3"]
        assert list(
            map(
                lambda job: job.metadata.name,
                jc._get_all_jobs("x", "b", "mas.ibm.com/job-cleanup-group", limit),
            )
        ) == ["job-xb-1", "job-xb-2"]
        assert list(
            map(
                lambda job: job.metadata.name,
                jc._get_all_jobs("x", "c", "mas.ibm.com/job-cleanup-group", limit),
            )
        ) == ["job-xc-1"]
        assert list(
            map(
                lambda job: job.metadata.name,
                jc._get_all_jobs("y", "a", "mas.ibm.com/job-cleanup-group", limit),
            )
        ) == ["job-ya-2", "job-ya-1"]
        assert (
            list(
                map(
                    lambda job: job.metadata.name,
                    jc._get_all_jobs("y", "b", "mas.ibm.com/job-cleanup-group", limit),
                )
            )
            == []
        )
        assert list(
            map(
                lambda job: job.metadata.name,
                jc._get_all_jobs("y", "a", "otherlabel", limit),
            )
        ) == ["job-yothera-1"]


@patch("kubernetes.client.BatchV1Api")
def test_cleanup_jobs(mock_batch_v1_api):
    mock_batch_v1_api.return_value.list_job_for_all_namespaces.side_effect = list_job_for_all_namespaces
    mock_batch_v1_api.return_value.list_namespaced_job.side_effect = list_namespaced_job

    jc = JobCleaner(None)
    for dry_run in [False, True]:
        dry_run_param = None
        if dry_run:
            dry_run_param = "All"

        expected_calls = [
            call("job-ya-1", "y", dry_run=dry_run_param, propagation_policy="Foreground"),
            call("job-xa-2", "x", dry_run=dry_run_param, propagation_policy="Foreground"),
            call("job-xa-1", "x", dry_run=dry_run_param, propagation_policy="Foreground"),
            call("job-xb-1", "x", dry_run=dry_run_param, propagation_policy="Foreground"),
        ]

        for limit in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
            mock_batch_v1_api.return_value.delete_namespaced_job.reset_mock()
            jc.cleanup_jobs("mas.ibm.com/job-cleanup-group", 3, dry_run)

            mock_batch_v1_api.return_value.delete_namespaced_job.assert_has_calls(expected_calls, any_order=True)

            assert mock_batch_v1_api.return_value.delete_namespaced_job.call_count == len(expected_calls)
