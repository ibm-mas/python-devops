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
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError, UnprocessibleEntityError

from jinja2 import Environment, FileSystemLoader

from .ocp import getConsoleURL, waitForCRD, waitForDeployment, crdExists, waitForPVC

logger = logging.getLogger(__name__)


def installOpenShiftPipelines(dynClient: DynamicClient, customStorageClassName: str = None) -> bool:
    """
    Install the OpenShift Pipelines Operator and wait for it to be ready to use.

    Creates the operator subscription, waits for the CRD and webhook to be ready,
    and handles PVC storage class configuration if needed.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        customStorageClassName (str, optional): Custom storage class name for Tekton PVC. Defaults to None.

    Returns:
        bool: True if installation is successful, False otherwise

    Raises:
        NotFoundError: If the package manifest is not found
        UnprocessibleEntityError: If the subscription cannot be created
    """
    packagemanifestAPI = dynClient.resources.get(api_version="packages.operators.coreos.com/v1", kind="PackageManifest")
    subscriptionsAPI = dynClient.resources.get(api_version="operators.coreos.com/v1alpha1", kind="Subscription")

    # Create the Operator Subscription
    try:
        if not crdExists(dynClient, "pipelines.tekton.dev"):
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
                subscription_name="openshift-pipelines-operator",
                subscription_namespace="openshift-operators",
                package_name="openshift-pipelines-operator-rh",
                package_channel=defaultChannel,
                catalog_name=catalogSource,
                catalog_namespace=catalogSourceNamespace
            )
            subscription = yaml.safe_load(renderedTemplate)
            subscriptionsAPI.apply(body=subscription, namespace="openshift-operators")

    except NotFoundError:
        logger.warning("Error: Couldn't find package manifest for Red Hat Openshift Pipelines Operator")
    except UnprocessibleEntityError:
        logger.warning("Error: Couldn't create/update OpenShift Pipelines Operator Subscription")

    # Wait for the CRD to be available
    logger.debug("Waiting for tasks.tekton.dev CRD to be available")
    foundReadyCRD = waitForCRD(dynClient, "tasks.tekton.dev")
    if foundReadyCRD:
        logger.info("OpenShift Pipelines Operator is installed and ready")
    else:
        logger.error("OpenShift Pipelines Operator is NOT installed and ready")
        return False

    # Wait for the webhook to be ready
    logger.debug("Waiting for tekton-pipelines-webhook Deployment to be ready")
    foundReadyWebhook = waitForDeployment(dynClient, namespace="openshift-pipelines", deploymentName="tekton-pipelines-webhook")
    if foundReadyWebhook:
        logger.info("OpenShift Pipelines Webhook is installed and ready")
    else:
        logger.error("OpenShift Pipelines Webhook is NOT installed and ready")
        return False

    # Workaround for bug in OpenShift Pipelines/Tekton
    # -------------------------------------------------------------------------
    # Wait for the postgredb-tekton-results-postgres-0 PVC to be ready
    # this PVC doesn't come up when there's no default storage class is in the cluster,
    # this is causing the pvc to be in pending state and causing the tekton-results-postgres statefulSet in pending,
    # due to these resources not coming up, the MAS pre-install check in the pipeline times out checking the health of this statefulSet,
    # causing failure in pipeline.
    # Refer https://github.com/ibm-mas/cli/issues/1511
    logger.debug("Waiting for postgredb-tekton-results-postgres-0 PVC to be ready")
    foundReadyPVC = waitForPVC(dynClient, namespace="openshift-pipelines", pvcName="postgredb-tekton-results-postgres-0")
    if foundReadyPVC:
        logger.info("OpenShift Pipelines postgres is installed and ready")
        return True
    else:
        tektonPVCisReady = addMissingStorageClassToTektonPVC(
            dynClient=dynClient,
            namespace="openshift-pipelines",
            pvcName="postgredb-tekton-results-postgres-0",
            storageClassName=customStorageClassName
        )
        if tektonPVCisReady:
            logger.info("OpenShift Pipelines postgres is installed and ready")
            return True
        else:
            logger.error("OpenShift Pipelines postgres PVC is NOT ready")
            return False


def addMissingStorageClassToTektonPVC(dynClient: DynamicClient, namespace: str, pvcName: str, storageClassName: str) -> bool:
    """
    OpenShift Pipelines has a problem when there is no default storage class defined in a cluster, this function
    patches the PVC used to store pipeline results to add a specific storage class into the PVC spec and waits for the
    PVC to be bound.

    :param dynClient: Kubernetes client, required to work with PVC
    :type dynClient: DynamicClient
    :param namespace: Namespace where OpenShift Pipelines is installed
    :type namespace: str
    :param pvcName: Name of the PVC that we want to fix
    :type pvcName: str
    :param storageClassName: Name of the storage class that we want to update the PVC to reference
    :type storageClassName: str
    :return: Description
    :rtype: bool
    """
    pvcAPI = dynClient.resources.get(api_version="v1", kind="PersistentVolumeClaim")
    try:
        pvc = pvcAPI.get(name=pvcName, namespace=namespace)
        if pvc.status.phase == "Pending" and pvc.spec.storageClassName is None:
            pvc.spec.storageClassName = storageClassName
            pvcAPI.patch(body=pvc, namespace=namespace)

            maxRetries = 60
            foundReadyPVC = False
            retries = 0
            while not foundReadyPVC and retries < maxRetries:
                retries += 1
                try:
                    patchedPVC = pvcAPI.get(name=pvcName, namespace=namespace)
                    if patchedPVC.status.phase == "Bound":
                        foundReadyPVC = True
                    else:
                        logger.debug(f"Waiting 5s for PVC {pvcName} to be bound before checking again ...")
                        sleep(5)
                except NotFoundError:
                    logger.error(f"The patched PVC {pvcName} does not exist.")
                    return False

            return foundReadyPVC

    except NotFoundError:
        logger.error(f"PVC {pvcName} does not exist")
        return False


def updateTektonDefinitions(namespace: str, yamlFile: str) -> None:
    """
    Install or update MAS Tekton pipeline and task definitions from a YAML file.

    Uses kubectl to apply a YAML file containing multiple resource types.

    Parameters:
        namespace (str): The namespace to apply the definitions to
        yamlFile (str): Path to the YAML file containing Tekton definitions

    Returns:
        None

    Raises:
        kubeconfig.exceptions.KubectlCommandError: If kubectl command fails
    """
    result = kubectl.run(subcmd_args=['apply', '-n', namespace, '-f', yamlFile])
    for line in result.split("\n"):
        logger.debug(line)


def preparePipelinesNamespace(dynClient: DynamicClient, instanceId: str = None, storageClass: str = None, accessMode: str = None, waitForBind: bool = True, configureRBAC: bool = True):
    """
    Prepare a namespace for MAS pipelines by creating RBAC and PVC resources.

    Creates cluster-wide or instance-specific pipeline namespace with necessary
    role bindings and persistent volume claims.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        instanceId (str, optional): MAS instance ID. If None, creates cluster-wide namespace. Defaults to None.
        storageClass (str, optional): Storage class for the PVC. Defaults to None.
        accessMode (str, optional): Access mode for the PVC. Defaults to None.
        waitForBind (bool, optional): Whether to wait for PVC to bind. Defaults to True.
        configureRBAC (bool, optional): Whether to configure RBAC. Defaults to True.

    Returns:
        None

    Raises:
        NotFoundError: If resources cannot be created
    """
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(
        loader=FileSystemLoader(searchpath=templateDir)
    )
    if instanceId is None:
        namespace = "mas-pipelines"
        template = env.get_template("pipelines-rbac-cluster.yml.j2")
    else:
        namespace = f"mas-{instanceId}-pipelines"
        template = env.get_template("pipelines-rbac.yml.j2")

    if configureRBAC:
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


def prepareAiServicePipelinesNamespace(dynClient: DynamicClient, instanceId: str = None, storageClass: str = None, accessMode: str = None, waitForBind: bool = True, configureRBAC: bool = True):
    """
    Prepare a namespace for AI Service pipelines by creating RBAC and PVC resources.

    Creates AI Service-specific pipeline namespace with necessary role bindings
    and persistent volume claims.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        instanceId (str, optional): AI Service instance ID. Defaults to None.
        storageClass (str, optional): Storage class for the PVC. Defaults to None.
        accessMode (str, optional): Access mode for the PVC. Defaults to None.
        waitForBind (bool, optional): Whether to wait for PVC to bind. Defaults to True.
        configureRBAC (bool, optional): Whether to configure RBAC. Defaults to True.

    Returns:
        None

    Raises:
        NotFoundError: If resources cannot be created
    """
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(
        loader=FileSystemLoader(searchpath=templateDir)
    )
    namespace = f"aiservice-{instanceId}-pipelines"
    template = env.get_template("aiservice-pipelines-rbac.yml.j2")

    if configureRBAC:
        # Create RBAC
        renderedTemplate = template.render(aiservice_instance_id=instanceId)
        logger.debug(renderedTemplate)
        crb = yaml.safe_load(renderedTemplate)
        clusterRoleBindingAPI = dynClient.resources.get(api_version="rbac.authorization.k8s.io/v1", kind="ClusterRoleBinding")
        clusterRoleBindingAPI.apply(body=crb, namespace=namespace)

    template = env.get_template("aiservice-pipelines-pvc.yml.j2")
    renderedTemplate = template.render(
        aiservice_instance_id=instanceId,
        pipeline_storage_class=storageClass,
        pipeline_storage_accessmode=accessMode
    )
    logger.debug(renderedTemplate)
    pvc = yaml.safe_load(renderedTemplate)
    pvcAPI = dynClient.resources.get(api_version="v1", kind="PersistentVolumeClaim")
    pvcAPI.apply(body=pvc, namespace=namespace)

    if waitForBind:
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


def prepareInstallSecrets(dynClient: DynamicClient, namespace: str, slsLicenseFile: str = None, additionalConfigs: dict = None, certs: str = None, podTemplates: str = None) -> None:
    """
    Create or update secrets required for MAS installation pipelines.

    Creates four secrets in the specified namespace: pipeline-additional-configs,
    pipeline-sls-entitlement, pipeline-certificates, and pipeline-pod-templates.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to create secrets in
        slsLicenseFile (str, optional): SLS license file content. Defaults to None (empty secret).
        additionalConfigs (dict, optional): Additional configuration data. Defaults to None (empty secret).
        certs (str, optional): Certificate data. Defaults to None (empty secret).
        podTemplates (str, optional): Pod template data. Defaults to None (empty secret).

    Returns:
        None

    Raises:
        NotFoundError: If secrets cannot be created
    """
    secretsAPI = dynClient.resources.get(api_version="v1", kind="Secret")

    # 1. Secret/pipeline-additional-configs
    # -------------------------------------------------------------------------
    # Must exist, but can be empty
    try:
        secretsAPI.delete(name="pipeline-additional-configs", namespace=namespace)
    except NotFoundError:
        pass

    if additionalConfigs is None:
        additionalConfigs = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {
                "name": "pipeline-additional-configs"
            }
        }
    secretsAPI.create(body=additionalConfigs, namespace=namespace)

    # 2. Secret/pipeline-sls-entitlement
    # -------------------------------------------------------------------------
    try:
        secretsAPI.delete(name="pipeline-sls-entitlement", namespace=namespace)
    except NotFoundError:
        pass

    if slsLicenseFile is None:
        slsLicenseFile = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {
                "name": "pipeline-sls-entitlement"
            }
        }
    secretsAPI.create(body=slsLicenseFile, namespace=namespace)

    # 3. Secret/pipeline-certificates
    # -------------------------------------------------------------------------
    # Must exist. It could be an empty secret at the first place before customer configure it
    try:
        secretsAPI.delete(name="pipeline-certificates", namespace=namespace)
    except NotFoundError:
        pass

    if certs is None:
        certs = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {
                "name": "pipeline-certificates"
            }
        }
    secretsAPI.create(body=certs, namespace=namespace)

    # 4. Secret/pipeline-pod-templates
    # -------------------------------------------------------------------------
    # Must exist, but can be empty
    try:
        secretsAPI.delete(name="pipeline-pod-templates", namespace=namespace)
    except NotFoundError:
        pass

    if podTemplates is None:
        podTemplates = {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {
                "name": "pipeline-pod-templates"
            }
        }
    secretsAPI.create(body=podTemplates, namespace=namespace)


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
                          skipPreCheck: bool = False,
                          masChannel: str = "",
                          params: dict = {}) -> str:
    """
    Create a PipelineRun to upgrade the chosen MAS instance
    """
    pipelineRunsAPI = dynClient.resources.get(api_version="tekton.dev/v1beta1", kind="PipelineRun")
    namespace = f"mas-{instanceId}-pipelines"
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    # Create the PipelineRun
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(
        loader=FileSystemLoader(searchpath=templateDir)
    )
    template = env.get_template("pipelinerun-upgrade.yml.j2")
    renderedTemplate = template.render(
        timestamp=timestamp,
        mas_instance_id=instanceId,
        skip_pre_check=skipPreCheck,
        mas_channel=masChannel,
        **params
    )
    logger.debug(renderedTemplate)
    pipelineRun = yaml.safe_load(renderedTemplate)
    pipelineRunsAPI.apply(body=pipelineRun, namespace=namespace)

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/mas-{instanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{instanceId}-upgrade-{timestamp}"
    return pipelineURL


def launchUninstallPipeline(dynClient: DynamicClient,
                            instanceId: str,
                            droNamespace: str,
                            uninstallCertManager: bool = False,
                            uninstallGrafana: bool = False,
                            uninstallCatalog: bool = False,
                            uninstallDRO: bool = False,
                            uninstallMongoDb: bool = False,
                            uninstallSLS: bool = False) -> str:
    """
    Create a PipelineRun to uninstall the chosen MAS instance (and selected dependencies)
    """
    pipelineRunsAPI = dynClient.resources.get(api_version="tekton.dev/v1beta1", kind="PipelineRun")
    namespace = f"mas-{instanceId}-pipelines"
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    # Create the PipelineRun
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(
        loader=FileSystemLoader(searchpath=templateDir)
    )
    template = env.get_template("pipelinerun-uninstall.yml.j2")

    grafanaAction = "uninstall" if uninstallGrafana else "none"
    certManagerAction = "uninstall" if uninstallCertManager else "none"
    ibmCatalogAction = "uninstall" if uninstallCatalog else "none"
    mongoDbAction = "uninstall" if uninstallMongoDb else "none"
    slsAction = "uninstall" if uninstallSLS else "none"
    droAction = "uninstall" if uninstallDRO else "none"

    # Render the pipelineRun
    renderedTemplate = template.render(
        timestamp=timestamp,
        mas_instance_id=instanceId,
        grafana_action=grafanaAction,
        cert_manager_action=certManagerAction,
        ibm_catalogs_action=ibmCatalogAction,
        mongodb_action=mongoDbAction,
        sls_action=slsAction,
        dro_action=droAction,
        dro_namespace=droNamespace
    )
    logger.debug(renderedTemplate)
    pipelineRun = yaml.safe_load(renderedTemplate)
    pipelineRunsAPI.apply(body=pipelineRun, namespace=namespace)

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/mas-{instanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{instanceId}-uninstall-{timestamp}"
    return pipelineURL


def launchPipelineRun(dynClient: DynamicClient, namespace: str, templateName: str, params: dict) -> str:
    """
    Launch a Tekton PipelineRun from a template.

    Creates a PipelineRun resource by rendering a Jinja2 template with the provided parameters.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        namespace (str): The namespace to create the PipelineRun in
        templateName (str): Name of the template file (without .yml.j2 extension)
        params (dict): Parameters to pass to the template

    Returns:
        str: Timestamp string used in the PipelineRun name (format: YYMMDD-HHMM)

    Raises:
        NotFoundError: If the template or namespace is not found
    """
    pipelineRunsAPI = dynClient.resources.get(api_version="tekton.dev/v1beta1", kind="PipelineRun")
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    # Create the PipelineRun
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(
        loader=FileSystemLoader(searchpath=templateDir)
    )
    template = env.get_template(f"{templateName}.yml.j2")

    # Render the pipelineRun
    renderedTemplate = template.render(
        timestamp=timestamp,
        **params
    )
    logger.debug(renderedTemplate)
    pipelineRun = yaml.safe_load(renderedTemplate)
    pipelineRunsAPI.apply(body=pipelineRun, namespace=namespace)
    return timestamp


def launchInstallPipeline(dynClient: DynamicClient, params: dict) -> str:
    """
    Create a PipelineRun to install a MAS or AI Service instance with selected dependencies.

    Automatically detects whether to install MAS or AI Service based on the presence
    of mas_instance_id in params.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        params (dict): Installation parameters including instance ID and configuration

    Returns:
        str: URL to the PipelineRun in the OpenShift console

    Raises:
        NotFoundError: If resources cannot be created
    """
    applicationType = "aiservice" if not params.get("mas_instance_id") else "mas"
    params["applicationType"] = applicationType
    instanceId = params[f"{applicationType}_instance_id"]
    namespace = f"{applicationType}-{instanceId}-pipelines"
    timestamp = launchPipelineRun(dynClient, namespace, "pipelinerun-install", params)

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/{applicationType}-{instanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{instanceId}-install-{timestamp}"
    return pipelineURL


def launchUpdatePipeline(dynClient: DynamicClient, params: dict) -> str:
    """
    Create a PipelineRun to update the Maximo Operator Catalog.

    Parameters:
        dynClient (DynamicClient): OpenShift Dynamic Client
        params (dict): Update parameters

    Returns:
        str: URL to the PipelineRun in the OpenShift console

    Raises:
        NotFoundError: If resources cannot be created
    """
    namespace = "mas-pipelines"
    timestamp = launchPipelineRun(dynClient, namespace, "pipelinerun-update", params)

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/mas-pipelines/tekton.dev~v1beta1~PipelineRun/mas-update-{timestamp}"
    return pipelineURL


def launchAiServiceUpgradePipeline(dynClient: DynamicClient,
                                   aiserviceInstanceId: str,
                                   skipPreCheck: bool = False,
                                   aiserviceChannel: str = "",
                                   params: dict = {}) -> str:
    """
    Create a PipelineRun to upgrade the chosen AI Service instance
    """
    pipelineRunsAPI = dynClient.resources.get(api_version="tekton.dev/v1beta1", kind="PipelineRun")
    namespace = f"aiservice-{aiserviceInstanceId}-pipelines"
    timestamp = datetime.now().strftime("%y%m%d-%H%M")
    # Create the PipelineRun
    templateDir = path.join(path.abspath(path.dirname(__file__)), "templates")
    env = Environment(
        loader=FileSystemLoader(searchpath=templateDir)
    )
    template = env.get_template("pipelinerun-aiservice-upgrade.yml.j2")
    renderedTemplate = template.render(
        timestamp=timestamp,
        aiservice_instance_id=aiserviceInstanceId,
        skip_pre_check=skipPreCheck,
        aiservice_channel=aiserviceChannel,
        **params
    )
    logger.debug(renderedTemplate)
    pipelineRun = yaml.safe_load(renderedTemplate)
    pipelineRunsAPI.apply(body=pipelineRun, namespace=namespace)

    pipelineURL = f"{getConsoleURL(dynClient)}/k8s/ns/aiservice-{aiserviceInstanceId}-pipelines/tekton.dev~v1beta1~PipelineRun/{aiserviceInstanceId}-upgrade-{timestamp}"
    return pipelineURL
