# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

import yaml
from unittest.mock import MagicMock, Mock
from openshift.dynamic.exceptions import NotFoundError

from mas.devops.restore import loadYamlFile, restoreResource


class TestLoadYamlFile:
    """Tests for loadYamlFile function"""

    def test_load_valid_yaml_file(self, tmp_path):
        """Test loading a valid YAML file"""
        yaml_content = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {
                'name': 'test-config',
                'namespace': 'test-ns'
            }
        }
        
        yaml_file = tmp_path / "test.yaml"
        with open(yaml_file, 'w') as f:
            yaml.dump(yaml_content, f)
        
        result = loadYamlFile(str(yaml_file))
        
        assert result is not None
        assert result['kind'] == 'ConfigMap'
        assert result['metadata']['name'] == 'test-config'

    def test_load_empty_yaml_file(self, tmp_path):
        """Test loading an empty YAML file"""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")
        
        result = loadYamlFile(str(yaml_file))
        
        assert result is None

    def test_load_nonexistent_file(self):
        """Test loading a non-existent file"""
        result = loadYamlFile("/nonexistent/path/file.yaml")
        
        assert result is None

    def test_load_invalid_yaml_file(self, tmp_path):
        """Test loading an invalid YAML file"""
        yaml_file = tmp_path / "invalid.yaml"
        yaml_file.write_text("invalid: yaml: content: [")
        
        result = loadYamlFile(str(yaml_file))
        
        assert result is None

    def test_load_yaml_with_multiple_documents(self, tmp_path):
        """Test loading YAML file with multiple documents returns None (not supported)"""
        yaml_file = tmp_path / "multi.yaml"
        yaml_file.write_text("---\nkey1: value1\n---\nkey2: value2")
        
        result = loadYamlFile(str(yaml_file))
        
        # yaml.safe_load() doesn't support multiple documents, so it should return None
        assert result is None


class TestRestoreResource:
    """Tests for restoreResource function"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_client = MagicMock()
        self.mock_resource_api = MagicMock()
        self.mock_client.resources.get.return_value = self.mock_resource_api

    def test_create_new_namespaced_resource(self):
        """Test creating a new namespaced resource"""
        resource_data = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {
                'name': 'test-config',
                'namespace': 'test-ns'
            },
            'data': {
                'key': 'value'
            }
        }
        
        # Resource doesn't exist
        self.mock_resource_api.get.side_effect = NotFoundError(Mock())
        
        success, name, status = restoreResource(self.mock_client, resource_data)
        
        assert success is True
        assert name == 'test-config'
        assert status is None
        self.mock_resource_api.create.assert_called_once_with(
            body=resource_data,
            namespace='test-ns'
        )

    def test_create_new_cluster_resource(self):
        """Test creating a new cluster-scoped resource"""
        resource_data = {
            'apiVersion': 'v1',
            'kind': 'Namespace',
            'metadata': {
                'name': 'test-namespace'
            }
        }
        
        # Resource doesn't exist
        self.mock_resource_api.get.side_effect = NotFoundError(Mock())
        
        success, name, status = restoreResource(self.mock_client, resource_data)
        
        assert success is True
        assert name == 'test-namespace'
        assert status is None
        self.mock_resource_api.create.assert_called_once_with(
            body=resource_data
        )

    def test_update_existing_resource_with_replace_true(self):
        """Test updating an existing resource when replace_resource is True"""
        resource_data = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {
                'name': 'test-config',
                'namespace': 'test-ns'
            },
            'data': {
                'key': 'new-value'
            }
        }
        
        # Resource exists
        existing_resource = {
            'metadata': {
                'name': 'test-config',
                'resourceVersion': '12345'
            }
        }
        self.mock_resource_api.get.return_value = existing_resource
        
        success, name, status = restoreResource(self.mock_client, resource_data, replace_resource=True)
        
        assert success is True
        assert name == 'test-config'
        assert status == 'updated'
        self.mock_resource_api.patch.assert_called_once_with(
            body=resource_data,
            name='test-config',
            namespace='test-ns',
            content_type='application/merge-patch+json'
        )

    def test_skip_existing_resource_with_replace_false(self):
        """Test skipping an existing resource when replace_resource is False"""
        resource_data = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {
                'name': 'test-config',
                'namespace': 'test-ns'
            }
        }
        
        # Resource exists
        existing_resource = {'metadata': {'name': 'test-config'}}
        self.mock_resource_api.get.return_value = existing_resource
        
        success, name, status = restoreResource(self.mock_client, resource_data, replace_resource=False)
        
        assert success is True
        assert name == 'test-config'
        assert status == 'skipped'
        self.mock_resource_api.patch.assert_not_called()
        self.mock_resource_api.create.assert_not_called()

    def test_namespace_override(self):
        """Test that namespace parameter overrides resource namespace"""
        resource_data = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {
                'name': 'test-config',
                'namespace': 'original-ns'
            }
        }
        
        # Resource doesn't exist
        self.mock_resource_api.get.side_effect = NotFoundError(Mock())
        
        success, name, status = restoreResource(
            self.mock_client,
            resource_data,
            namespace='override-ns'
        )
        
        assert success is True
        self.mock_resource_api.create.assert_called_once_with(
            body=resource_data,
            namespace='override-ns'
        )

    def test_missing_kind_field(self):
        """Test handling resource missing kind field"""
        resource_data = {
            'apiVersion': 'v1',
            'metadata': {
                'name': 'test-resource'
            }
        }
        
        success, name, status = restoreResource(self.mock_client, resource_data)
        
        assert success is False
        assert name == 'test-resource'
        assert 'missing required fields' in status.lower()

    def test_missing_api_version_field(self):
        """Test handling resource missing apiVersion field"""
        resource_data = {
            'kind': 'ConfigMap',
            'metadata': {
                'name': 'test-resource'
            }
        }
        
        success, name, status = restoreResource(self.mock_client, resource_data)
        
        assert success is False
        assert name == 'test-resource'
        assert 'missing required fields' in status.lower()

    def test_missing_name_field(self):
        """Test handling resource missing name field"""
        resource_data = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {}
        }
        
        success, name, status = restoreResource(self.mock_client, resource_data)
        
        assert success is False
        assert name == 'unknown'
        assert 'missing required fields' in status.lower()

    def test_create_failure(self):
        """Test handling create operation failure"""
        resource_data = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {
                'name': 'test-config',
                'namespace': 'test-ns'
            }
        }
        
        # Resource doesn't exist
        self.mock_resource_api.get.side_effect = NotFoundError(Mock())
        # Create fails
        self.mock_resource_api.create.side_effect = Exception("Create failed")
        
        success, name, status = restoreResource(self.mock_client, resource_data)
        
        assert success is False
        assert name == 'test-config'
        assert 'Failed to create' in status
        assert 'Create failed' in status

    def test_patch_failure(self):
        """Test handling patch operation failure"""
        resource_data = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {
                'name': 'test-config',
                'namespace': 'test-ns'
            }
        }
        
        # Resource exists
        existing_resource = {'metadata': {'name': 'test-config'}}
        self.mock_resource_api.get.return_value = existing_resource
        # Patch fails
        self.mock_resource_api.patch.side_effect = Exception("Patch failed")
        
        success, name, status = restoreResource(self.mock_client, resource_data, replace_resource=True)
        
        assert success is False
        assert name == 'test-config'
        assert 'Failed to update' in status
        assert 'Patch failed' in status

    def test_resource_api_get_failure(self):
        """Test handling failure to get resource API"""
        resource_data = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {
                'name': 'test-config'
            }
        }
        
        # Getting resource API fails
        self.mock_client.resources.get.side_effect = Exception("API not found")
        
        success, name, status = restoreResource(self.mock_client, resource_data)
        
        assert success is False
        assert name == 'test-config'
        assert 'Error restoring resource' in status

    def test_update_cluster_scoped_resource(self):
        """Test updating a cluster-scoped resource"""
        resource_data = {
            'apiVersion': 'v1',
            'kind': 'Namespace',
            'metadata': {
                'name': 'test-namespace'
            }
        }
        
        # Resource exists
        existing_resource = {'metadata': {'name': 'test-namespace'}}
        self.mock_resource_api.get.return_value = existing_resource
        
        success, name, status = restoreResource(self.mock_client, resource_data, replace_resource=True)
        
        assert success is True
        assert name == 'test-namespace'
        assert status == 'updated'
        self.mock_resource_api.patch.assert_called_once_with(
            body=resource_data,
            name='test-namespace',
            content_type='application/merge-patch+json'
        )

    def test_malformed_resource_data(self):
        """Test handling malformed resource data"""
        resource_data = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap'
            # Missing metadata entirely
        }
        
        success, name, status = restoreResource(self.mock_client, resource_data)
        
        assert success is False
        assert name == 'unknown'
        assert 'missing required fields' in status.lower()

    def test_resource_with_complex_metadata(self):
        """Test resource with complex metadata structure"""
        resource_data = {
            'apiVersion': 'apps/v1',
            'kind': 'Deployment',
            'metadata': {
                'name': 'test-deployment',
                'namespace': 'test-ns',
                'labels': {
                    'app': 'test',
                    'version': 'v1'
                },
                'annotations': {
                    'description': 'Test deployment'
                }
            },
            'spec': {
                'replicas': 3
            }
        }
        
        # Resource doesn't exist
        self.mock_resource_api.get.side_effect = NotFoundError(Mock())
        
        success, name, status = restoreResource(self.mock_client, resource_data)
        
        assert success is True
        assert name == 'test-deployment'
        assert status is None
        self.mock_resource_api.create.assert_called_once()