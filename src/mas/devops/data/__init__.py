# *****************************************************************************
# Copyright (c) 2024, 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************
"""
IBM Operator Catalog data management module.

This module provides functions to access and query IBM Operator Catalog definitions
stored as YAML files. Catalogs contain operator version information and are organized
by version tag and architecture.
"""

import yaml
from glob import glob
from os import path


class NoSuchCatalogError(Exception):
    pass


# Dev catalog IDs that resolve from Artifactory (not static yaml files).
# These use a rolling build so there is no fixed version metadata.
_DEV_CATALOG_PREFIXES = ("v9-master", "v9-dev")


def _isDevCatalogId(name: str) -> bool:
    """Return True if the catalog ID refers to a rolling dev/master catalog."""
    return any(name.startswith(prefix) for prefix in _DEV_CATALOG_PREFIXES)


def getCatalog(name: str) -> dict:
    """
    Load a specific IBM Operator Catalog definition by name.

    This function reads a catalog YAML file from the catalogs directory and returns
    its contents as a dictionary.

    For rolling dev catalogs (e.g. ``v9-master-amd64``), no static yaml file
    exists.  A minimal descriptor is returned instead so that callers do not
    need to special-case the dev-catalog path.

    Args:
        name (str): The catalog name/tag (e.g., "v9-241205-amd64", "v9-master-amd64").

    Returns:
        dict: The catalog definition dictionary containing operator versions and metadata.

    Raises:
        NoSuchCatalogError: If the specified catalog does not exist and is not a dev catalog.
    """
    # Dev/master catalogs are rolling builds served from Artifactory.
    # They have no static yaml descriptor — return a minimal placeholder so
    # that downstream logic (update validation, pipelinerun generation) can
    # proceed without crashing.
    if _isDevCatalogId(name):
        return {
            "apiVersion": "operators.coreos.com/v1alpha1",
            "kind": "CatalogSource",
            "metadata": {
                "name": "ibm-operator-catalog",
                "namespace": "openshift-marketplace",
            },
            "spec": {
                "displayName": f"IBM Maximo Operators ({name} Dev)",
                "image": f"docker-na-public.artifactory.swg-devops.com/wiotp-docker-local/cpopen/ibm-maximo-operator-catalog:{name}",
                "sourceType": "grpc",
                "publisher": "IBM",
            },
        }

    moduleFile = path.abspath(__file__)
    modulePath = path.dirname(moduleFile)
    catalogFileName = f"{name}.yaml"

    pathToCatalog = path.join(modulePath, "catalogs", catalogFileName)
    if not path.exists(pathToCatalog):
        raise NoSuchCatalogError(f"Catalog {name} is unknown: {pathToCatalog} does not exist")

    with open(pathToCatalog) as stream:
        return yaml.safe_load(stream)


def listCatalogTags(arch="amd64") -> list[str]:
    """
    List all available IBM Operator Catalog tags for a specific architecture.

    This function scans the catalogs directory and returns a sorted list of all
    catalog tags matching the specified architecture.

    Args:
        arch (str, optional): The target architecture (e.g., "amd64", "s390x", "ppc64le").
                             Defaults to "amd64".

    Returns:
        list: Sorted list of catalog tag strings (e.g., ["v8-240528-amd64", "v9-241205-amd64"]).
              Returns empty list if no catalogs are found for the architecture.
    """
    moduleFile = path.abspath(__file__)
    modulePath = path.dirname(moduleFile)
    yamlFiles = glob(path.join(modulePath, "catalogs", f"*-{arch}.yaml"))
    result = []
    for yamlFile in sorted(yamlFiles):
        result.append(path.basename(yamlFile).replace(".yaml", ""))
    return result


def getNewestCatalogTag(arch="amd64") -> str:
    """
    Get the most recent IBM Operator Catalog tag for a specific architecture.

    This function returns the newest (last in sorted order) catalog tag available
    for the specified architecture.

    Args:
        arch (str, optional): The target architecture (e.g., "amd64", "s390x", "ppc64le").
                             Defaults to "amd64".

    Returns:
        str: The newest catalog tag (e.g., "v9-241205-amd64").

    Raises:
        NoSuchCatalogError: If no catalogs are found for the specified architecture.
    """
    catalogs = listCatalogTags(arch)
    if len(catalogs) == 0:
        raise NoSuchCatalogError(f"There are no known catalogs for the {arch} platform")
    else:
        return catalogs[-1]


def getOCPLifecycleData() -> dict | None:
    """
    Load OpenShift Container Platform lifecycle data.

    This function reads the OCP lifecycle YAML file containing General Availability dates,
    Standard Support end dates, and Extended Update Support (EUS) end dates for various
    OCP versions.

    Returns:
        dict: The OCP lifecycle data dictionary with version information.
              Returns None if the ocp.yaml file doesn't exist.
    """
    moduleFile = path.abspath(__file__)
    modulePath = path.dirname(moduleFile)
    ocpFileName = "ocp.yaml"

    pathToOCP = path.join(modulePath, ocpFileName)
    if not path.exists(pathToOCP):
        return None

    with open(pathToOCP) as stream:
        return yaml.safe_load(stream)


def getOCPVersion(version: str) -> dict | None:
    """
    Get lifecycle information for a specific OCP version.

    This function retrieves the General Availability date, Standard Support end date,
    and Extended Update Support (EUS) end date for a specific OpenShift version.

    Args:
        version (str): The OCP version (e.g., "4.16", "4.17").

    Returns:
        dict: Dictionary containing 'ga_date', 'standard_support', and 'extended_support'.
              Returns None if the version is not found or OCP data doesn't exist.
    """
    ocpData = getOCPLifecycleData()
    if not ocpData:
        return None

    ocpVersions = ocpData.get("ocp_versions", {})
    return ocpVersions.get(version)


def listOCPVersions() -> list:
    """
    List all OCP versions with lifecycle data available.

    This function returns a sorted list of all OpenShift Container Platform versions
    that have lifecycle information defined.

    Returns:
        list: Sorted list of OCP version strings (e.g., ["4.12", "4.13", "4.14", ...]).
              Returns empty list if OCP data doesn't exist.
    """
    ocpData = getOCPLifecycleData()
    if not ocpData:
        return []

    ocpVersions = ocpData.get("ocp_versions", {})
    # Sort versions numerically (4.12, 4.13, etc.)
    return sorted(ocpVersions.keys(), key=lambda v: [int(x) for x in v.split(".")])


def getCatalogEditorial(catalogTag: str) -> dict | None:
    """
    Get editorial content (What's New and Known Issues) for a specific catalog.

    This function retrieves the editorial metadata from a catalog definition,
    which includes "What's New" highlights and "Known Issues" information.

    Args:
        catalogTag (str): The catalog tag (e.g., "v9-251231-amd64").

    Returns:
        dict: Dictionary with 'whats_new' and 'known_issues' keys containing
              structured lists. Returns None if catalog doesn't exist
              or has no editorial content.
    """
    catalog = getCatalog(catalogTag)

    return catalog.get("editorial")
