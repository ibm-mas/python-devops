# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

import logging
import yaml

from datetime import datetime
from os import path

from time import sleep

from kubeconfig import kubectl
from kubeconfig.exceptions import KubectlCommandError
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError, UnprocessibleEntityError

from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import TemplateNotFound

from .ocp import getConsoleURL, waitForCRD

logger = logging.getLogger(__name__)


def installOpenShiftPipelines(dynClient: DynamicClient) -> bool:
    """
    Install the OpenShift Pipelines Operator and wait for it to be ready to use
    """
    packagemanifestAPI = dynClient.resources.get(api_version="packages.operators.coreos.com/v1", kind="PackageManifest")
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")

    # Create the Operator Subscription
    try:
        manifest = packagemanifestAPI.get(name="openshift-pipelines-operator-rh", namespace="openshift-marketplace")
        defaultChannel = manifest.status.defaultChannel
        catalogSource = manifest.status.catalogSource
        catalogSourceNamespace = manifest.status.catalogSourceNamespace

        logger.info(f"OpenShift Pipelines Operator Details: {catalogSourceNamespace}/{catalogSource}@{defaultChannel}")

        templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
        env = Environment(
            loader=FileSystemLoader(searchpath=templateDir)
        )
        template = env.get_template("subscription.yml.j2")
        renderedTemplate = template.render(
            pipelines_channel=defaultChannel,
            pipelines_source=catalogSource,
            pipelines_source_namespace=catalogSourceNamespace
        )
        subscription = yaml.safe_load(renderedTemplate)
        subscriptionsAPI.apply(body=subscription, namespace="openshift-operators")

    except NotFoundError:
        logger.warning("Error: Couldn't find package manifest for Red Hat Openshift Pipelines Operator")
    except UnprocessibleEntityError:
        logger.warning("Error: Couldn't create/update OpenShift Pipelines Operator Subscription")

    foundReadyCRD = waitForCRD(dynClient, "tasks.tekton.dev")
    if foundReadyCRD:
        logger.info("OpenShift Pipelines Operator is installed and ready")
        return True
    else:
        logger.error("OpenShift Pipelines Operator is NOT installed and ready")
        return False


def updateTektonDefinitions(namespace: str, yamlFile: str) -> bool:
    """
    Install/update the MAS tekton pipeline and task definitions

    Unfortunately there's no API equivalent of what the kubectl CLI gives us with the ability to just apply a file containing a mix of
    """
    # https://github.com/gtaylor/kubeconfig-python/blob/master/kubeconfig/kubectl.py
    try:
        result = kubectl.run(subcmd_args=['apply', '-n', namespace, '-f', yamlFile])
        for line in result.split("\n"):
            logger.debug(line)
        return True
    except KubectlCommandError as e:
        logger.warning(f"Error: Unable to install/update Tekton definitions: {e}")
        return False


def preparePipelinesNamespace(dynClient: DynamicClient, instanceId: str=None, storageClass: str=None, accessMode: str=None, waitForBind: bool=True):
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(
        loader=FileSystemLoader(searchpath=templateDir)
    )

    if instanceId is None:
        namespace = f"mas-pipelines"
        template = env.get_template("pipelines-rbac-cluster.yml.j2")
    else:
        namespace = f"mas-{instanceId}-pipelines"
        template = env.get_template("pipelines-rbac.yml.j2")

    # Create RBAC
    renderedTemplate = template.render(mas_instance_id=instanceId)
    logger.debug(renderedTemplate)
    crb = yaml.safe_load(renderedTemplate)
    clusterRoleBindingAPI = dynClient.resources.get(api_version="rbac.authorization.k8s.io/v1", kind="ClusterRoleBinding")
    clusterRoleBindingAPI.apply(body=crb, namespace=namespace)

    # Create PVC (instanceId namespace only)
    if instanceId is not None:
        template = env.get_template("pipelines-pvc.yml.j2")
        renderedTemplate = template.render(
            mas_instance_id=instanceId,
            pipeline_storage_class=storageClass,
            pipeline_storage_accessmode=accessMode
        )
        logger.debug(renderedTemplate)
        pvc = yaml.safe_load(renderedTemplate)
        pvcAPI = dynClient.resources.get(api_version="v1", kind="PersistentVolumeClaim")
        pvcAPI.apply(body=pvc, namespace=namespace)

    if instanceId is not None and waitForBind:
        logger.debug("Waiting for PVC to be bound")
        pvcIsBound = False
        while not pvcIsBound:
            configPVC = pvcAPI.get(name="config-pvc", namespace=namespace)
            if configPVC.status.phase == "Bound":
                pvcIsBound = True
            else:
                logger.debug("Waiting 15s before checking status of PVC again")
                logger.debug(configPVC)
                sleep(15)

def prepareInstallSecrets(dynClient: DynamicClient, instanceId: str, slsLicenseFile: str, additionalConfigs: dict=None, podTemplatesDir: str=None) -> None:
    namespace=f"mas-{instanceId}-pipelines"
    secretsAPI = dynClient.resources.get(api_version="v1", kind="Secret")

    # Clean up existing secrets
    try:
        secretsAPI.delete(name="pipeline-additional-configs", namespace=namespace)
    except NotFoundError:
        pass
    try:
        secretsAPI.delete(name="pipeline-sls-entitlement", namespace=namespace)
    except NotFoundError:
        pass
    try:
        secretsAPI.delete(name="pipeline-pod-templates", namespace=namespace)
    except NotFoundError:
        pass
    try:
        secretsAPI.delete(name="pipeline-certificates", namespace=namespace)
    except NotFoundError:
        pass

    # Create new secrets
    if additionalConfigs is None:
        additionalConfigs={
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {
                "name": "pipeline-additional-configs"
            }
        }
    # pipeline-additional-configs must exist (otherwise the suite-install step will hang), but can be empty
    secretsAPI.create(body=additionalConfigs, namespace=namespace)

    result = kubectl.run(subcmd_args=['-n', namespace, 'create', 'secret', 'generic', 'pipeline-sls-entitlement', '--from-file', slsLicenseFile])
    for line in result.split("\n"):
        logger.debug(line)

    # pipeline-certificates must exist. It could be an empty secret at the first place before customer configure it
    result = kubectl.run(subcmd_args=['-n', namespace, 'create', 'secret', 'generic', 'pipeline-certificates'])
    for line in result.split("\n"):
        logger.debug(line)

    if podTemplatesDir is not None:
        podTemplatesCmd = [
            '-n', namespace, 'create', 'secret', 'generic', 'pipeline-pod-templates',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-bascfg.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-pushnotificationcfg.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-scimcfg.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-slscfg.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-smtpcfg.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-coreidp.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-suite.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-data-dictionary-assetdatadictionary.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-actions.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-auth.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-datapower.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-devops.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-dm.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-dsc.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-edgeconfig.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-fpl.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-guardian.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-iot.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-mbgx.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-mfgx.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-monitor.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-orgmgmt.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-provision.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-registry.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-state.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-iot-webui.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-manage-manageapp.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-manage-manageworkspace.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-manage-imagestitching.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-manage-manageaccelerators.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-manage-healthextaccelerator.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-manage-slackproxy.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-mas-manage-healthextworkspace.yml',
            '--from-file', f'{podTemplatesDir}:{podTemplatesDir}/ibm-sls-licenseservice.yml',
        ]
        result = kubectl.run(subcmd_args=podTemplatesCmd)
        for line in result.split("\n"):
            logger.debug(line)
    else:
        result = kubectl.run(subcmd_args=['-n', namespace, 'create', 'secret', 'generic', 'pipeline-pod-templates'])
        for line in result.split("\n"):
            logger.debug(line)

def testCLI() -> None:
    pass
    # echo -n "Testing availability of $CLI_IMAGE in cluster ..."
    # EXISTING_DEPLOYMENT_IMAGE=$(oc -n $PIPELINES_NS get deployment mas-cli -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null)

    # if [[ "$EXISTING_DEPLOYMENT_IMAGE" != "CLI_IMAGE" ]]
    # then oc -n $PIPELINES_NS apply -f $CONFIG_DIR/deployment-$MAS_INSTANCE_ID.yaml &>> $LOGFILE
    # fi

    # oc -n $PIPELINES_NS wait --for=condition=Available=true deployment mas-cli --timeout=3m &>> $LOGFILE
    # if [[ "$?" == "0" ]]; then
    #     # All is good
    #     echo -en "\033[1K" # Clear current line
    #     echo -en "\033[u" # Restore cursor position
    #     echo -e "${COLOR_GREEN}$CLI_IMAGE is available from the target OCP cluster${TEXT_RESET}"
    # else
    #     echo -en "\033[1K" # Clear current line
    #     echo -en "\033[u" # Restore cursor position

    #     # We can't get the image, so there's no point running the pipeline
    #     echo_warning "Failed to validate $CLI_IMAGE in the target OCP cluster"
    #     echo "This image must be accessible from your OpenShift cluster to run the installation:"
    #     echo "- If you are running an offline (air gap) installation this likely means you have not mirrored this image to your private registry"
    #     echo "- It could also mean that your cluster's ImageContentSourcePolicy is misconfigured and does not contain an entry for quay.io/ibmmas"
    #     echo "- Check the deployment status of mas-cli in your pipeline namespace. This will provide you with more information about the issue."

    #     echo -e "\n\n[WARNING] Failed to validate $CLI_IMAGE in the target OCP cluster" >> $LOGFILE
    #     echo_hr1 >> $LOGFILE
    #     oc -n $PIPELINES_NS get pods --selector="app=mas-cli" -o yaml >> $LOGFILE
    #     exit 1
    # fi

def launchUpgradePipeline(dynClient: DynamicClient,
                          instanceId: str,
                          masChannel: str = "") -> str:
    """
    Create a PipelineRun to upgrade the chosen MAS instance
    """
    pipelineRunsAPI = dynClient.resources.get(api_version="tekton.dev/v1beta1", kind="PipelineRun")
    namespace = f"mas-{instanceId}-pipelines"
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    # Create the PipelineRun
    try:
        templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
        env = Environment(
            loader=FileSystemLoader(searchpath=templateDir)
        )
        try:
            template = env.get_template("pipelinerun-upgrade.yml.j2")
        except TemplateNotFound as e:
            logger.warning(f"Could not find pipelinerun template in {templateDir}: {e}")
            return None
        renderedTemplate = template.render(
            timestamp=timestamp,
            mas_instance_id=instanceId,
            mas_channel=masChannel
        )
        # pipelineRun = yaml.safe_load(renderedTemplate)
        # pipelineRunsAPI.apply(body=pipelineRun, namespace=namespace)

    except Exception as e:
        logger.warning(f"Error: An unexpected error occured: {e}")
        logger.debug(renderedTemplate)
        return None

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/mas-{instanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{instanceId}-upgrade-{timestamp}"
    return pipelineURL

def launchUninstallPipeline(dynClient: DynamicClient,
                            instanceId: str,
                            certManagerProvider: str = "redhat",
                            uninstallCertManager: bool = False,
                            uninstallGrafana: bool = False,
                            uninstallCatalog: bool = False,
                            uninstallCommonServices: bool = False,
                            uninstallUDS: bool = False,
                            uninstallMongoDb: bool = False,
                            uninstallSLS: bool = False) -> str:
    """
    Create a PipelineRun to uninstall the chosen MAS instance (and selected dependencies)
    """
    pipelineRunsAPI = dynClient.resources.get(api_version="tekton.dev/v1beta1", kind="PipelineRun")
    namespace = f"mas-{instanceId}-pipelines"
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    # Create the PipelineRun
    try:
        templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
        env = Environment(
            loader=FileSystemLoader(searchpath=templateDir)
        )
        try:
            template = env.get_template("pipelinerun-uninstall.yml.j2")
        except TemplateNotFound as e:
            logger.warning(f"Could not find pipelinerun template in {templateDir}: {e}")
            return None

        grafanaAction = "uninstall" if uninstallGrafana else "none"
        certManagerAction = "uninstall" if uninstallCertManager else "none"
        commonServicesAction = "uninstall" if uninstallCommonServices else "none"
        ibmCatalogAction = "uninstall" if uninstallCatalog else "none"
        mongoDbAction = "uninstall" if uninstallMongoDb else "none"
        slsAction = "uninstall" if uninstallSLS else "none"
        udsAction = "uninstall" if uninstallUDS else "none"

        # Render the pipelineRun
        renderedTemplate = template.render(
            timestamp=timestamp,
            mas_instance_id=instanceId,
            grafana_action=grafanaAction,
            cert_manager_provider=certManagerProvider,
            cert_manager_action=certManagerAction,
            common_services_action=commonServicesAction,
            ibm_catalogs_action=ibmCatalogAction,
            mongodb_action=mongoDbAction,
            sls_action=slsAction,
            uds_action=udsAction
        )
        pipelineRun = yaml.safe_load(renderedTemplate)
        pipelineRunsAPI.apply(body=pipelineRun, namespace=namespace)

    except Exception as e:
        logger.warning(f"Error: An unexpected error occured: {e}")
        logger.debug(renderedTemplate)
        return None

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/mas-{instanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{instanceId}-uninstall-{timestamp}"
    return pipelineURL

def launchInstallPipeline(dynClient: DynamicClient,
                          params: dict) -> str:
    """
    Create a PipelineRun to install the chosen MAS instance (and selected dependencies)
    """

    instanceId = params["mas_instance_id"]

    pipelineRunsAPI = dynClient.resources.get(api_version="tekton.dev/v1beta1", kind="PipelineRun")
    namespace = f"mas-{instanceId}-pipelines"
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    # Create the PipelineRun
    try:
        templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
        env = Environment(
            loader=FileSystemLoader(searchpath=templateDir)
        )
        try:
            template = env.get_template("pipelinerun-install.yml.j2")
        except TemplateNotFound as e:
            logger.warning(f"Could not find pipelinerun template in {templateDir}: {e}")
            return None

        # Render the pipelineRun
        renderedTemplate = template.render(
            timestamp=timestamp,
            **params
        )
        logger.debug(renderedTemplate)
        pipelineRun = yaml.safe_load(renderedTemplate)
        pipelineRunsAPI.apply(body=pipelineRun, namespace=namespace)

    except Exception as e:
        logger.warning(f"Error: An unexpected error occured: {e}")
        return None

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/mas-{instanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{instanceId}-install-{timestamp}"
    return pipelineURL
