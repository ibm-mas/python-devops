# *****************************************************************************
# Copyright (c) 2024 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************
import yaml
from glob import glob
from os import path


def getCatalog(name: str) -> dict:
    moduleFile = path.abspath(__file__)
    modulePath = path.dirname(moduleFile)
    catalogFileName = f"{name}.yaml"

    pathToCatalog = path.join(modulePath, "catalogs", catalogFileName)
    if not path.exists(pathToCatalog):
        return None

    with open(pathToCatalog) as stream:
        return yaml.safe_load(stream)


def listCatalogTags(arch="amd64") -> list:
    moduleFile = path.abspath(__file__)
    modulePath = path.dirname(moduleFile)
    yamlFiles = glob(path.join(modulePath, "catalogs", f"*-{arch}.yaml"))
    result = []
    for yamlFile in sorted(yamlFiles):
        result.append(path.basename(yamlFile).replace(".yaml", ""))
    return result


def getNewestCatalogTag(arch="amd64") -> str:
    catalogs = listCatalogTags(arch)
    if len(catalogs) == 0:
        return None
    else:
        return catalogs[-1]
