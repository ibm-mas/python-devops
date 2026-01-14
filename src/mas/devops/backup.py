# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************
import logging
import os
import yaml
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError

logger = logging.getLogger(name=__name__)


def createBackupDirectories(paths: list) -> bool:
    """
    Create backup directories if they do not exist
    """
    try:
        for path in paths:
            os.makedirs(path, exist_ok=True)
            logger.info(msg=f"Created backup directory: {path}")
        return True
    except Exception as e:
        logger.error(msg=f"Error creating backup directories: {e}")
        return False


def copyContentsToYamlFile(file_path: str, content: dict) -> bool:
    """
    Write dictionary content to a YAML file
    """
    try:
        # Create a custom dumper that uses literal style for multi-line strings
        class LiteralDumper(yaml.SafeDumper):
            pass

        def str_representer(dumper, data):
            if '\n' in data:
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)

        LiteralDumper.add_representer(str, str_representer)

        with open(file_path, 'w') as yaml_file:
            yaml.dump(content, yaml_file, default_flow_style=False, Dumper=LiteralDumper)
        return True
    except Exception as e:
        logger.error(f"Error writing to YAML file {file_path}: {e}")
        return False


def filterResourceData(data: dict) -> dict:
    """
    Filter metadata from Resource data and create minimal dict
    """
    metadata_fields_to_remove = [
        'annotations',
        'creationTimestamp',
        'generation',
        'resourceVersion',
        'selfLink',
        'ownerReferences'
        'uid',
        'managedFields'
    ]
    filteredCopy = data.copy()
    if 'metadata' in filteredCopy:
        for field in metadata_fields_to_remove:
            if field in filteredCopy['metadata']:
                del filteredCopy['metadata'][field]

    if 'status' in filteredCopy:
        del filteredCopy['status']

    return filteredCopy


def extract_secrets_from_dict(data, secret_names=None):
    """
    Recursively extract secret names from a dictionary structure.
    Looks for keys like 'secretName' and 'secretRef.name' and collects their values.

    Args:
        data: Dictionary to search
        secret_names: Set to collect secret names (created if None)

    Returns:
        Set of secret names found
    """
    if secret_names is None:
        secret_names = set()

    if isinstance(data, dict):
        for key, value in data.items():
            # Check if this key is 'secretName' and has a string value
            if (key == 'secretName' or 'secretname' in key.lower()) and isinstance(value, str) and value:
                secret_names.add(value)
            # Check if this key contains 'secretRef' and contains a 'name' field
            elif 'SecretRef' in key and isinstance(value, dict):
                if 'name' in value and isinstance(value['name'], str) and value['name']:
                    secret_names.add(value['name'])
            # Recursively search nested structures
            elif isinstance(value, (dict, list)):
                extract_secrets_from_dict(value, secret_names)

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                extract_secrets_from_dict(item, secret_names)

    return secret_names


def backupResources(dynClient: DynamicClient, kind: str, api_version: str, backup_path: str, namespace=None, name=None, labels=None) -> tuple:
    """
    Backup resources of a given kind.
    If name is provided, backs up that specific resource.
    If name is None, backs up all resources of that kind.
    If namespace is None, backs up cluster-level resources.
    If labels is provided, filters resources by label selectors.

    Args:
        dynClient: Kubernetes dynamic client
        kind: Resource kind (e.g., 'MongoCfg', 'Secret', 'ClusterRole')
        api_version: API version (e.g., 'config.mas.ibm.com/v1')
        backup_path: Path to save backup files
        namespace: Optional namespace to backup from (None for cluster-level resources)
        name: Optional specific resource name
        labels: Optional list of label selectors (e.g., ['app=myapp', 'env=prod'])

    Returns:
        tuple: (backed_up_count: int, not_found_count: int, failed_count: int, discovered_secrets: set)
    """
    discovered_secrets = set()
    backed_up_count = 0
    not_found_count = 0
    failed_count = 0

    # Build label selector string if labels provided
    label_selector = None
    if labels:
        label_selector = ','.join(labels)

    # Determine scope description for logging
    scope_desc = f"namespace '{namespace}'" if namespace else "cluster-level"
    label_desc = f" with labels [{label_selector}]" if label_selector else ""

    try:
        resourceAPI = dynClient.resources.get(api_version=api_version, kind=kind)

        if name:
            # Backup specific named resource
            logger.info(f"Backing up {kind} '{name}' from {scope_desc} (API version: {api_version}){label_desc}")
            try:
                if namespace:
                    resource = resourceAPI.get(name=name, namespace=namespace)
                else:
                    resource = resourceAPI.get(name=name)

                if resource:
                    resources_to_process = [resource]
                else:
                    logger.info(f"{kind} '{name}' not found in {scope_desc}, skipping backup")
                    not_found_count = 1
                    return (backed_up_count, not_found_count, failed_count, discovered_secrets)
            except NotFoundError:
                logger.error(f"{kind} '{name}' not found in {scope_desc}, skipping backup")
                not_found_count = 1
                return (backed_up_count, not_found_count, failed_count, discovered_secrets)
        else:
            # Backup all resources of this kind
            logger.info(f"Backing up all {kind} resources from {scope_desc} (API version: {api_version}){label_desc}")

            # Build get parameters
            get_params = {}
            if namespace:
                get_params['namespace'] = namespace
            if label_selector:
                get_params['label_selector'] = label_selector

            resources = resourceAPI.get(**get_params)
            resources_to_process = resources.items

        # Process each resource
        for resource in resources_to_process:
            resource_name = resource["metadata"]["name"]
            resource_dict = resource.to_dict()

            # Extract secrets from this resource if it's not a Secret itself
            if kind != 'Secret':
                secrets = extract_secrets_from_dict(resource_dict.get('spec', {}))
                if secrets:
                    logger.info(f"Found {len(secrets)} secret reference(s) in {kind} '{resource_name}': {', '.join(sorted(secrets))}")
                    discovered_secrets.update(secrets)

            # Backup the resource
            resource_backup_path = f"{backup_path}/resources/{kind.lower()}s"
            createBackupDirectories([resource_backup_path])
            resource_file_path = f"{resource_backup_path}/{resource_name}.yaml"
            filtered_resource = filterResourceData(resource_dict)
            if copyContentsToYamlFile(resource_file_path, filtered_resource):
                logger.info(f"Successfully backed up {kind} '{resource_name}' to '{resource_file_path}'")
                backed_up_count += 1
            else:
                logger.error(f"Failed to back up {kind} '{resource_name}' to '{resource_file_path}'")
                failed_count += 1

        if backed_up_count > 0:
            logger.info(f"Successfully backed up {backed_up_count} {kind} resource(s)")
        elif not name:
            logger.info(f"No {kind} resources found in {scope_desc}{label_desc}")

        return (backed_up_count, not_found_count, failed_count, discovered_secrets)

    except NotFoundError:
        if name:
            logger.info(f"{kind} '{name}' not found in {scope_desc}")
            not_found_count = 1
        else:
            logger.info(f"No {kind} resources found in {scope_desc}{label_desc}")
        return (backed_up_count, not_found_count, failed_count, discovered_secrets)
    except Exception as e:
        logger.error(f"Error backing up {kind} resources: {e}")
        failed_count = 1
        return (backed_up_count, not_found_count, failed_count, discovered_secrets)
