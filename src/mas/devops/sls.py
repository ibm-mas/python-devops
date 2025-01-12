import logging
from openshift.dynamic import DynamicClient

logger = logging.getLogger(__name__)


def listSLSInstances(dynClient: DynamicClient) -> list:
    """
    Get a list of SLS instances on the cluster
    """
    slsAPI = dynClient.resources.get(api_version="sls.ibm.com/v1", kind="LicenseService")

    licenseservices = slsAPI.get().to_dict()['items']

    numSLS = len(licenseservices)

    if numSLS == 1:
        logger.info("There is 1 SLS instance installed on this cluster:")
        logger.info(f" * {licenseservices[0]['metadata']['name']} ({{licenseservices[0]['metadata']['namespace']}}) v{licenseservices[0]['status']['versions']['reconciled']}")
    elif numSLS > 0:
        logger.info(f"There are {numSLS} SLS instances installed on this cluster:")
        for licenseservice in licenseservices:
            logger.info(f" * {licenseservice['metadata']['name']} ({{licenseservice['metadata']['namespace']}}) v{licenseservice['status']['versions']['reconciled']}")
    else:
        logger.info("There are no SLS instances installed on this cluster")
    return licenseservices
