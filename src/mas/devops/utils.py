"""
Utility functions for version comparison and other common operations.

This module provides semantic version comparison utilities with custom handling
for pre-release versions and wildcard version strings.
"""

import logging
import re
import semver
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


def isVersionBefore(_compare_to_version, _current_version):
    """
    Check if the current version is before (older than) the comparison version.

    This function performs a modified semantic version comparison where pre-release
    versions are treated as equal to their base release version. For example,
    '8.6.0-pre.m1dev86' is normalized to '8.6.0' before comparison. Wildcard versions
    like '8.6.x' are converted to '8.6.0'.

    Args:
        _compare_to_version (str): The version to compare against (e.g., "8.6.0").
        _current_version (str): The current version to check (e.g., "8.5.0" or "8.6.0-pre.m1dev86").
                               Can be None, in which case False is returned.

    Returns:
        bool: True if current_version < compare_to_version, False otherwise.
              Returns False if _current_version is None.

    Note:
        This differs from strict semantic versioning where pre-release versions
        are considered less than their base version.
    """
    if _current_version is None:
        print("Version is not informed. Returning False")
        return False

    strippedVersion = _current_version.split("-")[0]
    if ".x" in strippedVersion:
        strippedVersion = strippedVersion.replace(".x", ".0")
    current_version = semver.VersionInfo.parse(strippedVersion)
    compareToVersion = semver.VersionInfo.parse(_compare_to_version)
    return current_version.compare(compareToVersion) < 0


def isVersionEqualOrAfter(_compare_to_version, _current_version):
    """
    Check if the current version is equal to or after (newer than) the comparison version.

    This function performs a modified semantic version comparison where pre-release
    versions are treated as equal to their base release version. For example,
    '8.6.0-pre.m1dev86' is normalized to '8.6.0' before comparison. Wildcard versions
    like '8.6.x' are converted to '8.6.0'.

    Args:
        _compare_to_version (str): The version to compare against (e.g., "8.6.0").
        _current_version (str): The current version to check (e.g., "8.7.0" or "8.6.0-pre.m1dev86").
                               Can be None, in which case False is returned.

    Returns:
        bool: True if current_version >= compare_to_version, False otherwise.
              Returns False if _current_version is None.

    Note:
        This differs from strict semantic versioning where pre-release versions
        are considered less than their base version.
    """
    if _current_version is None:
        print("Version is not informed. Returning False")
        return False

    strippedVersion = _current_version.split("-")[0]
    if ".x" in strippedVersion:
        strippedVersion = strippedVersion.replace(".x", ".0")
    current_version = semver.VersionInfo.parse(strippedVersion)
    compareToVersion = semver.VersionInfo.parse(_compare_to_version)
    return current_version.compare(compareToVersion) >= 0


def validateIBMEntitlementKey(entitlementKey: str, repository: str = "cp/mas/coreapi", timeout: int = 30) -> bool:
    """Validate IBM entitlement key against cp.icr.io registry.

    This function validates an IBM entitlement key by attempting to obtain
    an authentication token from the IBM Container Registry and verifying
    access to the specified repository.

    Args:
        entitlementKey (str): IBM entitlement key to validate.
        repository (str, optional): Repository to test access against. Defaults to "cp/mas/coreapi".
        timeout (int, optional): Request timeout in seconds. Defaults to 30.

    Returns:
        bool: True if key is valid and grants access to the repository, False otherwise.

    Raises:
        requests.exceptions.RequestException: If network request fails.
    """
    try:
        registry_url = f"https://cp.icr.io/v2/{repository}/tags/list"
        logger.debug(f"Validating entitlement key against {repository}")

        # First request without auth to get the auth challenge
        response = requests.get(registry_url, timeout=timeout)

        if response.status_code == 401:
            # Parse WWW-Authenticate header to get token endpoint
            auth_header = response.headers.get("WWW-Authenticate", "")
            logger.debug(f"Auth challenge received: {auth_header[:100]}...")

            # Extract realm and service from auth header
            realm_match = re.search(r'realm="([^"]+)"', auth_header)
            service_match = re.search(r'service="([^"]+)"', auth_header)
            scope_match = re.search(r'scope="([^"]+)"', auth_header)

            if not realm_match:
                logger.error("Could not parse authentication realm")
                return False

            token_url = realm_match.group(1)
            params = {}

            if service_match:
                params["service"] = service_match.group(1)
            if scope_match:
                params["scope"] = scope_match.group(1)
            else:
                params["scope"] = f"repository:{repository}:pull"

            logger.debug(f"Token endpoint: {token_url}")

            # Get authentication token
            token_response = requests.get(token_url, params=params, auth=HTTPBasicAuth("cp", entitlementKey), timeout=timeout)

            if token_response.status_code != 200:
                logger.error(f"Failed to get token (HTTP {token_response.status_code})")
                return False

            token_data = token_response.json()
            token = token_data.get("token") or token_data.get("access_token")

            if not token:
                logger.error("No token received - invalid entitlement key")
                return False

            # Validate token by accessing registry
            logger.debug("Validating token against registry")
            headers = {"Authorization": f"Bearer {token}"}
            validate_response = requests.get(registry_url, headers=headers, timeout=timeout)

            if validate_response.status_code == 200:
                logger.info(f"Valid entitlement key with access to {repository}")
                return True
            else:
                logger.error(f"Token validation failed (HTTP {validate_response.status_code})")
                return False

        elif response.status_code == 200:
            logger.info("Registry accessible without authentication (public repository)")
            return True
        else:
            logger.error(f"Unexpected response (HTTP {response.status_code})")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        raise
