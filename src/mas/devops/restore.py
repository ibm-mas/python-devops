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
import yaml
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError, ResourceNotFoundError

logger = logging.getLogger(name=__name__)


def loadYamlFile(file_path: str):
    """
    Load YAML content from a file

    Args:
        file_path: Path to the YAML file

    Returns:
        dict: Parsed YAML content or None if error
    """
    try:
        with open(file_path, "r") as yaml_file:
            content = yaml.safe_load(yaml_file)
        return content
    except Exception as e:
        logger.error(f"Error reading YAML file {file_path}: {e}")
        return None


def restoreResource(dynClient: DynamicClient, resource_data: dict, namespace=None, replace_resource=True) -> tuple:
    """
    Restore a single Kubernetes resource from its YAML representation.
    If the resource exists and replace_resource is True, it will be updated (replaced).
    If the resource exists and replace_resource is False, it will be skipped.
    If the resource doesn't exist, it will be created.

    Args:
        dynClient: Kubernetes dynamic client
        resource_data: Dictionary containing the resource definition
        namespace: Optional namespace override (uses resource's namespace if not provided)
        replace_resource: If True, replace existing resources; if False, skip them (default: True)

    Returns:
        tuple: (success: bool, resource_name: str, status_message: str or None)
        - success: True if created, updated, or skipped; False if failed
        - resource_name: Name of the resource
        - status_message: None if created, "updated" if replaced, "skipped" if exists and not replaced, error message if failed
    """
    try:
        # Extract resource metadata
        kind = resource_data.get("kind")
        api_version = resource_data.get("apiVersion")
        metadata = resource_data.get("metadata", {})
        resource_name = metadata.get("name")
        resource_namespace = namespace or metadata.get("namespace")

        if not kind or not api_version or not resource_name:
            error_msg = "Resource missing required fields (kind, apiVersion, or name)"
            logger.error(error_msg)
            return (False, resource_name or "unknown", error_msg)

        # Get the resource API
        resourceAPI = dynClient.resources.get(api_version=api_version, kind=kind)

        # Determine scope description for logging
        scope_desc = f"namespace '{resource_namespace}'" if resource_namespace else "cluster-level"

        # Check if resource already exists
        resource_exists = False
        existing_resource = None
        try:
            if resource_namespace:
                existing_resource = resourceAPI.get(name=resource_name, namespace=resource_namespace)
            else:
                existing_resource = resourceAPI.get(name=resource_name)
            resource_exists = existing_resource is not None
        except NotFoundError:
            resource_exists = False

        # Apply the resource (create, update, or skip)
        try:
            if resource_exists:
                if replace_resource:
                    # Resource exists - update it using strategic merge patch
                    logger.info(f"Patching existing {kind} '{resource_name}' in {scope_desc}")

                    if resource_namespace:
                        resourceAPI.patch(
                            body=resource_data,
                            name=resource_name,
                            namespace=resource_namespace,
                            content_type="application/merge-patch+json",
                        )
                    else:
                        resourceAPI.patch(
                            body=resource_data,
                            name=resource_name,
                            content_type="application/merge-patch+json",
                        )
                    logger.info(f"Successfully patched {kind} '{resource_name}' in {scope_desc}")
                    return (True, resource_name, "updated")
                else:
                    # Resource exists but replace_resource is False - skip it
                    logger.info(f"{kind} '{resource_name}' already exists in {scope_desc}, skipping (replace_resource=False)")
                    return (True, resource_name, "skipped")
            else:
                # Resource doesn't exist - create it
                logger.info(f"Creating {kind} '{resource_name}' in {scope_desc}")
                if resource_namespace:
                    resourceAPI.create(body=resource_data, namespace=resource_namespace)
                else:
                    resourceAPI.create(body=resource_data)
                logger.info(f"Successfully created {kind} '{resource_name}' in {scope_desc}")
                return (True, resource_name, None)
        except Exception as e:
            action = "update" if resource_exists else "create"
            error_msg = f"Failed to {action} {kind} '{resource_name}': {e}"
            logger.error(error_msg)
            return (False, resource_name, error_msg)

    except ResourceNotFoundError:
        return (True, resource_data.get("kind"), "skipped")

    except Exception as e:
        error_msg = f"Error restoring resource: {e}"
        logger.error(error_msg)
        return (
            False,
            resource_data.get("metadata", {}).get("name", "unknown"),
            error_msg,
        )
