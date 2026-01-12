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

from mas.devops.backup import createBackupDirectories, copyContentsToYamlFile, filterResourceData


class TestCreateBackupDirectories:
    """Tests for createBackupDirectories function"""

    def test_create_single_directory(self, tmp_path):
        """Test creating a single backup directory"""
        test_dir = tmp_path / "backup1"
        result = createBackupDirectories([str(test_dir)])
        
        assert result is True
        assert test_dir.exists()
        assert test_dir.is_dir()

    def test_create_multiple_directories(self, tmp_path):
        """Test creating multiple backup directories"""
        test_dirs = [
            tmp_path / "backup1",
            tmp_path / "backup2",
            tmp_path / "backup3"
        ]
        paths = [str(d) for d in test_dirs]
        result = createBackupDirectories(paths)
        
        assert result is True
        for test_dir in test_dirs:
            assert test_dir.exists()
            assert test_dir.is_dir()

    def test_create_nested_directories(self, tmp_path):
        """Test creating nested backup directories"""
        nested_dir = tmp_path / "level1" / "level2" / "level3"
        result = createBackupDirectories([str(nested_dir)])
        
        assert result is True
        assert nested_dir.exists()
        assert nested_dir.is_dir()

    def test_create_existing_directory(self, tmp_path):
        """Test creating a directory that already exists"""
        test_dir = tmp_path / "existing"
        test_dir.mkdir()
        
        result = createBackupDirectories([str(test_dir)])
        
        assert result is True
        assert test_dir.exists()

    def test_create_empty_list(self):
        """Test with empty list of paths"""
        result = createBackupDirectories([])
        assert result is True

    def test_create_directory_permission_error(self, mocker):
        """Test handling of permission errors"""
        mock_makedirs = mocker.patch('os.makedirs', side_effect=PermissionError("Permission denied"))
        
        result = createBackupDirectories(["/invalid/path"])
        
        assert result is False
        mock_makedirs.assert_called_once()

    def test_create_directory_os_error(self, mocker):
        """Test handling of OS errors"""
        mocker.patch('os.makedirs', side_effect=OSError("OS error"))
        
        result = createBackupDirectories(["/some/path"])
        
        assert result is False


class TestCopyContentsToYamlFile:
    """Tests for copyContentsToYamlFile function"""

    def test_write_simple_dict(self, tmp_path):
        """Test writing a simple dictionary to YAML file"""
        test_file = tmp_path / "test.yaml"
        content = {"key1": "value1", "key2": "value2"}
        
        result = copyContentsToYamlFile(str(test_file), content)
        
        assert result is True
        assert test_file.exists()
        
        with open(test_file, 'r') as f:
            loaded_content = yaml.safe_load(f)
        assert loaded_content == content

    def test_write_nested_dict(self, tmp_path):
        """Test writing a nested dictionary to YAML file"""
        test_file = tmp_path / "nested.yaml"
        content = {
            "level1": {
                "level2": {
                    "level3": "value"
                }
            },
            "list": [1, 2, 3]
        }
        
        result = copyContentsToYamlFile(str(test_file), content)
        
        assert result is True
        with open(test_file, 'r') as f:
            loaded_content = yaml.safe_load(f)
        assert loaded_content == content

    def test_write_empty_dict(self, tmp_path):
        """Test writing an empty dictionary"""
        test_file = tmp_path / "empty.yaml"
        content = {}
        
        result = copyContentsToYamlFile(str(test_file), content)
        
        assert result is True
        with open(test_file, 'r') as f:
            loaded_content = yaml.safe_load(f)
        assert loaded_content == content

    def test_overwrite_existing_file(self, tmp_path):
        """Test overwriting an existing YAML file"""
        test_file = tmp_path / "overwrite.yaml"
        old_content = {"old": "data"}
        new_content = {"new": "data"}
        
        # Write initial content
        with open(test_file, 'w') as f:
            yaml.dump(old_content, f)
        
        # Overwrite with new content
        result = copyContentsToYamlFile(str(test_file), new_content)
        
        assert result is True
        with open(test_file, 'r') as f:
            loaded_content = yaml.safe_load(f)
        assert loaded_content == new_content
        assert loaded_content != old_content

    def test_write_to_nonexistent_directory(self, tmp_path):
        """Test writing to a file in a non-existent directory"""
        test_file = tmp_path / "nonexistent" / "test.yaml"
        content = {"key": "value"}
        
        result = copyContentsToYamlFile(str(test_file), content)
        
        assert result is False

    def test_write_permission_error(self, mocker):
        """Test handling of permission errors during write"""
        mocker.patch('builtins.open', side_effect=PermissionError("Permission denied"))
        
        result = copyContentsToYamlFile("/invalid/path.yaml", {"key": "value"})
        
        assert result is False

    def test_write_with_special_characters(self, tmp_path):
        """Test writing content with special characters"""
        test_file = tmp_path / "special.yaml"
        content = {
            "special": "value with\nnewlines",
            "unicode": "café ☕",
            "quotes": "value with 'quotes' and \"double quotes\""
        }
        
        result = copyContentsToYamlFile(str(test_file), content)
        
        assert result is True
        with open(test_file, 'r') as f:
            loaded_content = yaml.safe_load(f)
        assert loaded_content == content


class TestFilterResourceData:
    """Tests for filterResourceData function"""

    def test_filter_all_metadata_fields(self):
        """Test filtering all metadata fields that should be removed"""
        data = {
            "apiVersion": "v1",
            "kind": "Resource",
            "metadata": {
                "name": "test-resource",
                "namespace": "test-namespace",
                "annotations": {"key": "value"},
                "creationTimestamp": "2026-01-01T00:00:00Z",
                "generation": 1,
                "resourceVersion": "12345",
                "selfLink": "/api/v1/namespaces/test/resources/test-resource",
                "uid": "abc-123-def",
                "managedFields": [{"manager": "test"}]
            },
            "spec": {"replicas": 3}
        }
        
        result = filterResourceData(data)
        
        assert "name" in result["metadata"]
        assert "namespace" in result["metadata"]
        assert "annotations" not in result["metadata"]
        assert "creationTimestamp" not in result["metadata"]
        assert "generation" not in result["metadata"]
        assert "resourceVersion" not in result["metadata"]
        assert "selfLink" not in result["metadata"]
        assert "uid" not in result["metadata"]
        assert "managedFields" not in result["metadata"]
        assert "spec" in result

    def test_filter_status_field(self):
        """Test that status field is removed"""
        data = {
            "metadata": {"name": "test"},
            "spec": {"replicas": 3},
            "status": {
                "phase": "Running",
                "conditions": []
            }
        }
        
        result = filterResourceData(data)
        
        assert "status" not in result
        assert "spec" in result
        assert "metadata" in result

    def test_filter_partial_metadata(self):
        """Test filtering when only some metadata fields are present"""
        data = {
            "metadata": {
                "name": "test-resource",
                "uid": "abc-123",
                "labels": {"app": "test"}
            }
        }
        
        result = filterResourceData(data)
        
        assert "name" in result["metadata"]
        assert "labels" in result["metadata"]
        assert "uid" not in result["metadata"]

    def test_filter_no_metadata(self):
        """Test filtering when metadata field is not present"""
        data = {
            "apiVersion": "v1",
            "kind": "Resource",
            "spec": {"replicas": 3}
        }
        
        result = filterResourceData(data)
        
        assert "metadata" not in result
        assert "spec" in result
        assert "apiVersion" in result

    def test_filter_empty_metadata(self):
        """Test filtering with empty metadata"""
        data = {
            "metadata": {},
            "spec": {"replicas": 3}
        }
        
        result = filterResourceData(data)
        
        assert "metadata" in result
        assert result["metadata"] == {}

    def test_filter_preserves_other_fields(self):
        """Test that other fields are preserved"""
        data = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "test-config",
                "uid": "should-be-removed"
            },
            "data": {
                "key1": "value1",
                "key2": "value2"
            }
        }
        
        result = filterResourceData(data)
        
        assert result["apiVersion"] == "v1"
        assert result["kind"] == "ConfigMap"
        assert result["data"] == {"key1": "value1", "key2": "value2"}
        assert "uid" not in result["metadata"]

    def test_filter_shallow_copy_behavior(self):
        """Test that filterResourceData uses shallow copy (modifies nested dicts)"""
        data = {
            "metadata": {
                "name": "test",
                "uid": "abc-123"
            },
            "status": {"phase": "Running"}
        }
        
        result = filterResourceData(data)
        
        # Due to shallow copy, nested metadata dict is modified in original
        # but top-level status is not (it's deleted from copy only)
        assert "uid" not in data["metadata"]  # Modified due to shallow copy
        assert "status" in data  # Not modified (top-level key)
        
        # Result should not have uid and status
        assert "uid" not in result["metadata"]
        assert "status" not in result

    def test_filter_complex_resource(self):
        """Test filtering a complex Kubernetes resource"""
        data = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "my-deployment",
                "namespace": "default",
                "labels": {"app": "myapp"},
                "annotations": {"deployment.kubernetes.io/revision": "1"},
                "creationTimestamp": "2026-01-01T00:00:00Z",
                "generation": 5,
                "resourceVersion": "98765",
                "uid": "xyz-789",
                "managedFields": [{"manager": "kubectl"}]
            },
            "spec": {
                "replicas": 3,
                "selector": {"matchLabels": {"app": "myapp"}}
            },
            "status": {
                "availableReplicas": 3,
                "readyReplicas": 3
            }
        }
        
        result = filterResourceData(data)
        
        # Check preserved fields
        assert result["apiVersion"] == "apps/v1"
        assert result["kind"] == "Deployment"
        assert result["metadata"]["name"] == "my-deployment"
        assert result["metadata"]["namespace"] == "default"
        assert result["metadata"]["labels"] == {"app": "myapp"}
        assert result["spec"]["replicas"] == 3
        
        # Check removed fields
        assert "annotations" not in result["metadata"]
        assert "creationTimestamp" not in result["metadata"]
        assert "generation" not in result["metadata"]
        assert "resourceVersion" not in result["metadata"]
        assert "uid" not in result["metadata"]
        assert "managedFields" not in result["metadata"]
        assert "status" not in result

    def test_filter_empty_dict(self):
        """Test filtering an empty dictionary"""
        data = {}
        result = filterResourceData(data)
        assert result == {}

# Made with Bob
