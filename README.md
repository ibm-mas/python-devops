mas.devops
===============================================================================
[![Code style: PEP8](https://img.shields.io/badge/code%20style-PEP--8-blue.svg)](https://peps.python.org/pep-0008/)
[![Flake8: checked](https://img.shields.io/badge/flake8-checked-blueviolet)](https://flake8.pycqa.org/en/latest/)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ibm-mas/python-devops/python-release.yml)
[![PyPI - Version](https://img.shields.io/pypi/v/mas.devops)](https://pypi.org/project/mas-devops)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/mas.devops)
![PyPI - Downloads](https://img.shields.io/pypi/dm/mas.devops)


Example
-------------------------------------------------------------------------------
```python
from openshift import dynamic
from kubernetes import config
from kubernetes.client import api_client

from mas.devops.ocp import createNamespace
from mas.devops.tekton import installOpenShiftPipelines, updateTektonDefinitions, launchUpgradePipeline

instanceId = "mymas"
pipelinesNamespace = f"mas-{instanceId}-pipelines"

# Create an OpenShift client
dynClient = dynamic.DynamicClient(
    api_client.ApiClient(configuration=config.load_kube_config())
)

# Install OpenShift Pipelines Operator
installOpenShiftPipelines(dynamicClient)

# Create the pipelines namespace and install the MAS tekton definitions
createNamespace(dynamicClient, pipelinesNamespace)
updateTektonDefinitions(pipelinesNamespace, "/mascli/templates/ibm-mas-tekton.yaml")

# Launch the upgrade pipeline and print the URL to view the pipeline run
pipelineURL = launchUpgradePipeline(self.dynamicClient, instanceId)
print(pipelineURL)
```

mas-devops-create-initial-users
---------------------------------------------


Add to /etc/hosts
```
127.0.0.1               tgk01-masdev.mas-tgk01-manage.svc.cluster.local
127.0.0.1               coreapi.mas-tgk01-core.svc.cluster.local
127.0.0.1               admin-dashboard.mas-tgk01-core.svc.cluster.local
```

```bash
SM_AWS_REGION=""
SM_AWS_ACCESS_KEY_ID=""
SM_AWS_SECRET_ACCESS_KEY=""

aws configure set default.region ${SM_AWS_REGION}
aws configure set aws_access_key_id ${SM_AWS_ACCESS_KEY_ID}
aws configure set aws_secret_access_key ${SM_AWS_SECRET_ACCESS_KEY}


oc login --token=sha256~xxx --server=https://xxx:6443

oc port-forward service/admin-dashboard 8445:443 -n mas-tgk01-core
oc port-forward service/coreapi 8444:443 -n mas-tgk01-core
oc port-forward service/tgk01-masdev 8443:443 -n mas-tgk01-manage

mas-devops-create-initial-users-for-saas \
    --mas-instance-id tgk01 \
    --mas-workspace-id masdev \
    --log-level INFO \
    --initial-users-secret-name "aws-dev/noble4/tgk01/initial_users" \
    --manage-api-port 8443 \
    --coreapi-port 8444 \
    --admin-dashboard-port 8445
    

mas-devops-create-initial-users-for-saas \
    --mas-instance-id tgk01 \
    --mas-workspace-id masdev \
    --log-level INFO \
    --initial-users-yaml-file /home/tom/workspaces/notes/mascore3423/example-users-single.yaml \
    --manage-api-port 8443 \
    --coreapi-port 8444 \
    --admin-dashboard-port 8445
```

Example of initial_users secret:
```json
{"john.smith1@example.com":"primary,john1,smith1","john.smith2@example.com":"primary,john2,smith2","john.smith3@example.com":"secondary,john3,smith3"}
```

