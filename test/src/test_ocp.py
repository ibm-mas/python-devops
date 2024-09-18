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
import yaml


from mas.devops import ocp


def test_execInPod_success(mocker):

  mock_CoreV1Api = mocker.patch('kubernetes.client.CoreV1Api')
  mock_core_v1_api = mock_CoreV1Api.return_value

  # Mock the `stream` function and the request object it returns
  mock_stream = mocker.patch('mas.devops.ocp.stream')
  
  # Mock the response of the `stream` function
  mock_req = mock_stream.return_value
  mock_req.run_forever.return_value = None
  mock_req.read_stdout.return_value = "mock_stdout"
  mock_req.read_stderr.return_value = "mock_stderr"
  mock_req.read_channel.return_value = yaml.dump({"status": "Success"})

  o = ocp.execInPod(mock_core_v1_api, 'pod_name', 'namespace', ['command'])
  assert o ==  "mock_stdout"


def test_execInPod_failure(mocker):

  mock_CoreV1Api = mocker.patch('kubernetes.client.CoreV1Api')
  mock_core_v1_api = mock_CoreV1Api.return_value

  # Mock the `stream` function and the request object it returns
  mock_stream = mocker.patch('mas.devops.ocp.stream')
  
  # Mock the response of the `stream` function
  mock_req = mock_stream.return_value
  mock_req.run_forever.return_value = None
  mock_req.read_stdout.return_value = "mock_stdout"
  mock_req.read_stderr.return_value = "mock_stderr"
  mock_req.read_channel.return_value = yaml.dump({"status": "Failure"})

  with pytest.raises(Exception, match=r"Failed to execute \['command'\] on pod_name in namespace namespace: None. stdout: mock_stdout, stderr: mock_stderr"):
    ocp.execInPod(mock_core_v1_api, 'pod_name', 'namespace', ['command'])
