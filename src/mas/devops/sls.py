import logging
import requests
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError, ResourceNotFoundError, UnauthorizedError

logger = logging.getLogger(__name__)


def listSLSInstances(dynClient: DynamicClient) -> list:
    """
    Get a list of SLS instances on the cluster
    """
    try:
        slsAPI = dynClient.resources.get(api_version="sls.ibm.com/v1", kind="LicenseService")
        return slsAPI.get().to_dict()['items']
    except NotFoundError:
        logger.info("There are no SLS instances installed on this cluster")
        return []
    except ResourceNotFoundError:
        logger.info("LicenseService CRD not found on cluster")
        return []
    except UnauthorizedError:
        logger.error("Error: Unable to verify SLS instances due to failed authorization: {e}")
        return []


def verifySLSConnection(sls_url: str, server_ca: str) -> bool:
    logger.info("Checking SLS connection")
    response = requests.get(f"{sls_url}/api/probes/readiness", verify=server_ca)
    if response.status_code == 200:
        return True
    return False
