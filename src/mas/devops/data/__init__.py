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
