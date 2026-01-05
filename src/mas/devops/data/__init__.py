# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
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


def getCatalog(name: str) -> dict | None:
    """
    Load a specific IBM Operator Catalog definition by name.

    This function reads a catalog YAML file from the catalogs directory and returns
    its contents as a dictionary.

    Args:
        name (str): The catalog name/tag (e.g., "v9-241205-amd64", "v8-240528-amd64").

    Returns:
        dict: The catalog definition dictionary containing operator versions and metadata.
              Returns None if the catalog file doesn't exist.
    """
    moduleFile = path.abspath(__file__)
    modulePath = path.dirname(moduleFile)
    catalogFileName = f"{name}.yaml"

    pathToCatalog = path.join(modulePath, "catalogs", catalogFileName)
    if not path.exists(pathToCatalog):
        return None

    with open(pathToCatalog) as stream:
        return yaml.safe_load(stream)


def listCatalogTags(arch="amd64") -> list:
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


def getNewestCatalogTag(arch="amd64") -> str | None:
    """
    Get the most recent IBM Operator Catalog tag for a specific architecture.

    This function returns the newest (last in sorted order) catalog tag available
    for the specified architecture.

    Args:
        arch (str, optional): The target architecture (e.g., "amd64", "s390x", "ppc64le").
                             Defaults to "amd64".

    Returns:
        str: The newest catalog tag (e.g., "v9-241205-amd64").
             Returns None if no catalogs are found for the architecture.
    """
    catalogs = listCatalogTags(arch)
    if len(catalogs) == 0:
        return None
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
    if not catalog:
        return None

    return catalog.get("editorial")
