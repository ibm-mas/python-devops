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
from unittest.mock import MagicMock, Mock, patch
from kubernetes.dynamic.exceptions import NotFoundError

from mas.devops.backup import (
    createBackupDirectories,
    copyContentsToYamlFile,
    filterResourceData,
    backupResources,
    extract_secrets_from_dict,
)


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
        test_dirs = [tmp_path / "backup1", tmp_path / "backup2", tmp_path / "backup3"]
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

    def test_create_directory_permission_error(self):
        """Test handling of permission errors"""
        with patch("os.makedirs", side_effect=PermissionError("Permission denied")) as mock_makedirs:
            result = createBackupDirectories(["/invalid/path"])

        assert result is False
        mock_makedirs.assert_called_once()

    def test_create_directory_os_error(self):
        """Test handling of OS errors"""
        with patch("os.makedirs", side_effect=OSError("OS error")):
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

        with open(test_file, "r") as f:
            loaded_content = yaml.safe_load(f)
        assert loaded_content == content

    def test_write_nested_dict(self, tmp_path):
        """Test writing a nested dictionary to YAML file"""
        test_file = tmp_path / "nested.yaml"
        content = {"level1": {"level2": {"level3": "value"}}, "list": [1, 2, 3]}

        result = copyContentsToYamlFile(str(test_file), content)

        assert result is True
        with open(test_file, "r") as f:
            loaded_content = yaml.safe_load(f)
        assert loaded_content == content

    def test_write_empty_dict(self, tmp_path):
        """Test writing an empty dictionary"""
        test_file = tmp_path / "empty.yaml"
        content = {}

        result = copyContentsToYamlFile(str(test_file), content)

        assert result is True
        with open(test_file, "r") as f:
            loaded_content = yaml.safe_load(f)
        assert loaded_content == content

    def test_overwrite_existing_file(self, tmp_path):
        """Test overwriting an existing YAML file"""
        test_file = tmp_path / "overwrite.yaml"
        old_content = {"old": "data"}
        new_content = {"new": "data"}

        # Write initial content
        with open(test_file, "w") as f:
            yaml.dump(old_content, f)

        # Overwrite with new content
        result = copyContentsToYamlFile(str(test_file), new_content)

        assert result is True
        with open(test_file, "r") as f:
            loaded_content = yaml.safe_load(f)
        assert loaded_content == new_content
        assert loaded_content != old_content

    def test_write_to_nonexistent_directory(self, tmp_path):
        """Test writing to a file in a non-existent directory"""
        test_file = tmp_path / "nonexistent" / "test.yaml"
        content = {"key": "value"}

        result = copyContentsToYamlFile(str(test_file), content)

        assert result is False

    def test_write_permission_error(self):
        """Test handling of permission errors during write"""
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            result = copyContentsToYamlFile("/invalid/path.yaml", {"key": "value"})

        assert result is False

    def test_write_with_special_characters(self, tmp_path):
        """Test writing content with special characters"""
        test_file = tmp_path / "special.yaml"
        content = {
            "special": "value with\nnewlines",
            "unicode": "café ☕",
            "quotes": "value with 'quotes' and \"double quotes\"",
        }

        result = copyContentsToYamlFile(str(test_file), content)

        assert result is True
        with open(test_file, "r") as f:
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
                "managedFields": [{"manager": "test"}],
            },
            "spec": {"replicas": 3},
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
            "status": {"phase": "Running", "conditions": []},
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
                "labels": {"app": "test"},
            }
        }

        result = filterResourceData(data)

        assert "name" in result["metadata"]
        assert "labels" in result["metadata"]
        assert "uid" not in result["metadata"]

    def test_filter_no_metadata(self):
        """Test filtering when metadata field is not present"""
        data = {"apiVersion": "v1", "kind": "Resource", "spec": {"replicas": 3}}

        result = filterResourceData(data)

        assert "metadata" not in result
        assert "spec" in result
        assert "apiVersion" in result

    def test_filter_empty_metadata(self):
        """Test filtering with empty metadata"""
        data = {"metadata": {}, "spec": {"replicas": 3}}

        result = filterResourceData(data)

        assert "metadata" in result
        assert result["metadata"] == {}

    def test_filter_preserves_other_fields(self):
        """Test that other fields are preserved"""
        data = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "test-config", "uid": "should-be-removed"},
            "data": {"key1": "value1", "key2": "value2"},
        }

        result = filterResourceData(data)

        assert result["apiVersion"] == "v1"
        assert result["kind"] == "ConfigMap"
        assert result["data"] == {"key1": "value1", "key2": "value2"}
        assert "uid" not in result["metadata"]

    def test_filter_shallow_copy_behavior(self):
        """Test that filterResourceData uses shallow copy (modifies nested dicts)"""
        data = {
            "metadata": {"name": "test", "uid": "abc-123"},
            "status": {"phase": "Running"},
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
                "managedFields": [{"manager": "kubectl"}],
            },
            "spec": {"replicas": 3, "selector": {"matchLabels": {"app": "myapp"}}},
            "status": {"availableReplicas": 3, "readyReplicas": 3},
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


class TestExtractSecretsFromDict:
    """Tests for extract_secrets_from_dict function"""

    def test_extract_single_secret(self):
        """Test extracting a single secret name"""
        data = {"spec": {"secretName": "my-secret"}}
        result = extract_secrets_from_dict(data)
        assert result == {"my-secret"}

    def test_extract_multiple_secrets(self):
        """Test extracting multiple secret names"""
        data = {
            "spec": {
                "database": {"secretName": "db-secret"},
                "auth": {"secretName": "auth-secret"},
            }
        }
        result = extract_secrets_from_dict(data)
        assert result == {"db-secret", "auth-secret"}

    def test_extract_secrets_from_list(self):
        """Test extracting secrets from list structures"""
        data = {
            "spec": {
                "volumes": [
                    {"secretName": "secret1"},
                    {"secretName": "secret2"},
                    {"configMap": "not-a-secret"},
                ]
            }
        }
        result = extract_secrets_from_dict(data)
        assert result == {"secret1", "secret2"}

    def test_extract_nested_secrets(self):
        """Test extracting deeply nested secrets"""
        data = {"level1": {"level2": {"level3": {"secretName": "deep-secret"}}}}
        result = extract_secrets_from_dict(data)
        assert result == {"deep-secret"}

    def test_no_secrets_found(self):
        """Test when no secrets are present"""
        data = {"spec": {"replicas": 3, "image": "myapp:latest"}}
        result = extract_secrets_from_dict(data)
        assert result == set()

    def test_empty_dict(self):
        """Test with empty dictionary"""
        result = extract_secrets_from_dict({})
        assert result == set()

    def test_ignore_empty_secret_name(self):
        """Test that empty string secret names are ignored"""
        data = {"spec": {"secretName": "", "other": {"secretName": "valid-secret"}}}
        result = extract_secrets_from_dict(data)
        assert result == {"valid-secret"}

    def test_ignore_non_string_secret_name(self):
        """Test that non-string secret names are ignored"""
        data = {"spec": {"secretName": 123, "other": {"secretName": "valid-secret"}}}
        result = extract_secrets_from_dict(data)
        assert result == {"valid-secret"}

    def test_duplicate_secrets(self):
        """Test that duplicate secret names are deduplicated"""
        data = {
            "spec": {
                "volume1": {"secretName": "shared-secret"},
                "volume2": {"secretName": "shared-secret"},
                "volume3": {"secretName": "unique-secret"},
            }
        }
        result = extract_secrets_from_dict(data)
        assert result == {"shared-secret", "unique-secret"}


class TestBackupResources:
    """Tests for backupResources function"""

    def test_backup_single_namespaced_resource(self, tmp_path):
        """Test backing up a single namespaced resource by name"""
        backup_path = str(tmp_path / "backup")

        # Mock resource data
        mock_resource = {
            "metadata": {
                "name": "test-resource",
                "namespace": "test-ns",
                "uid": "abc-123",
            },
            "spec": {"replicas": 3},
        }

        # Create mock resource object with to_dict method
        mock_resource_obj = MagicMock()
        mock_resource_obj.__getitem__ = lambda self, key: mock_resource[key]
        mock_resource_obj.to_dict.return_value = mock_resource

        # Mock the dynamic client
        mock_client = MagicMock()
        mock_api = MagicMock()
        mock_api.get.return_value = mock_resource_obj
        mock_client.resources.get.return_value = mock_api

        with patch("mas.devops.backup.copyContentsToYamlFile", return_value=True):
            result = backupResources(
                mock_client,
                kind="ConfigMap",
                api_version="v1",
                backup_path=backup_path,
                namespace="test-ns",
                name="test-resource",
            )

        backed_up, not_found, failed, secrets = result
        assert backed_up == 1
        assert not_found == 0
        assert failed == 0
        assert secrets == set()

    def test_backup_multiple_namespaced_resources(self, tmp_path):
        """Test backing up all resources of a kind in a namespace"""
        backup_path = str(tmp_path / "backup")

        # Mock multiple resources
        mock_resources = [
            {
                "metadata": {"name": "resource1", "namespace": "test-ns"},
                "spec": {"data": "value1"},
            },
            {
                "metadata": {"name": "resource2", "namespace": "test-ns"},
                "spec": {"data": "value2"},
            },
        ]

        # Create mock resource objects
        mock_resource_objs = []
        for res in mock_resources:
            mock_obj = MagicMock()
            mock_obj.__getitem__ = lambda self, key, r=res: r[key]
            mock_obj.to_dict.return_value = res
            mock_resource_objs.append(mock_obj)

        # Mock the response with items
        mock_response = MagicMock()
        mock_response.items = mock_resource_objs

        # Mock the dynamic client
        mock_client = MagicMock()
        mock_api = MagicMock()
        mock_api.get.return_value = mock_response
        mock_client.resources.get.return_value = mock_api

        with patch("mas.devops.backup.copyContentsToYamlFile", return_value=True):
            result = backupResources(
                mock_client,
                kind="ConfigMap",
                api_version="v1",
                backup_path=backup_path,
                namespace="test-ns",
            )

        backed_up, not_found, failed, secrets = result
        assert backed_up == 2
        assert not_found == 0
        assert failed == 0

    def test_backup_cluster_level_resource(self, tmp_path):
        """Test backing up cluster-level resources (no namespace)"""
        backup_path = str(tmp_path / "backup")

        mock_resource = {
            "metadata": {"name": "cluster-role"},
            "rules": [{"apiGroups": ["*"], "resources": ["*"], "verbs": ["*"]}],
        }

        mock_resource_obj = MagicMock()
        mock_resource_obj.__getitem__ = lambda self, key: mock_resource[key]
        mock_resource_obj.to_dict.return_value = mock_resource

        mock_client = MagicMock()
        mock_api = MagicMock()
        mock_api.get.return_value = mock_resource_obj
        mock_client.resources.get.return_value = mock_api

        with patch("mas.devops.backup.copyContentsToYamlFile", return_value=True):
            result = backupResources(
                mock_client,
                kind="ClusterRole",
                api_version="rbac.authorization.k8s.io/v1",
                backup_path=backup_path,
                name="cluster-role",
            )

        backed_up, not_found, failed, secrets = result
        assert backed_up == 1
        assert not_found == 0
        assert failed == 0

    def test_backup_with_label_selector(self, tmp_path):
        """Test backing up resources with label selectors"""
        backup_path = str(tmp_path / "backup")

        mock_resource = {
            "metadata": {
                "name": "labeled-resource",
                "namespace": "test-ns",
                "labels": {"app": "myapp", "env": "prod"},
            },
            "spec": {},
        }

        mock_resource_obj = MagicMock()
        mock_resource_obj.__getitem__ = lambda self, key: mock_resource[key]
        mock_resource_obj.to_dict.return_value = mock_resource

        mock_response = MagicMock()
        mock_response.items = [mock_resource_obj]

        mock_client = MagicMock()
        mock_api = MagicMock()
        mock_api.get.return_value = mock_response
        mock_client.resources.get.return_value = mock_api

        with patch("mas.devops.backup.copyContentsToYamlFile", return_value=True):
            result = backupResources(
                mock_client,
                kind="ConfigMap",
                api_version="v1",
                backup_path=backup_path,
                namespace="test-ns",
                labels=["app=myapp", "env=prod"],
            )

        backed_up, not_found, failed, secrets = result
        assert backed_up == 1
        assert not_found == 0
        assert failed == 0

        # Verify label selector was passed correctly
        mock_api.get.assert_called_once_with(namespace="test-ns", label_selector="app=myapp,env=prod")

    def test_backup_resource_not_found_by_name(self):
        """Test handling when a specific named resource is not found"""
        mock_client = MagicMock()
        mock_api = MagicMock()
        mock_api.get.side_effect = NotFoundError(Mock())
        mock_client.resources.get.return_value = mock_api

        result = backupResources(
            mock_client,
            kind="ConfigMap",
            api_version="v1",
            backup_path="/tmp/backup",
            namespace="test-ns",
            name="nonexistent",
        )

        backed_up, not_found, failed, secrets = result
        assert backed_up == 0
        assert not_found == 1
        assert failed == 0
        assert secrets == set()

    def test_backup_no_resources_found(self):
        """Test when no resources of the kind exist"""
        mock_response = MagicMock()
        mock_response.items = []

        mock_client = MagicMock()
        mock_api = MagicMock()
        mock_api.get.return_value = mock_response
        mock_client.resources.get.return_value = mock_api

        result = backupResources(
            mock_client,
            kind="ConfigMap",
            api_version="v1",
            backup_path="/tmp/backup",
            namespace="test-ns",
        )

        backed_up, not_found, failed, secrets = result
        assert backed_up == 0
        assert not_found == 0
        assert failed == 0

    def test_backup_discovers_secrets(self, tmp_path):
        """Test that secrets are discovered from resource specs"""
        backup_path = str(tmp_path / "backup")

        mock_resource = {
            "metadata": {"name": "app-deployment", "namespace": "test-ns"},
            "spec": {
                "template": {
                    "spec": {
                        "volumes": [
                            {"secretName": "db-credentials"},
                            {"secretName": "api-key"},
                        ]
                    }
                }
            },
        }

        mock_resource_obj = MagicMock()
        mock_resource_obj.__getitem__ = lambda self, key: mock_resource[key]
        mock_resource_obj.to_dict.return_value = mock_resource

        mock_client = MagicMock()
        mock_api = MagicMock()
        mock_api.get.return_value = mock_resource_obj
        mock_client.resources.get.return_value = mock_api

        with patch("mas.devops.backup.copyContentsToYamlFile", return_value=True):
            result = backupResources(
                mock_client,
                kind="Deployment",
                api_version="apps/v1",
                backup_path=backup_path,
                namespace="test-ns",
                name="app-deployment",
            )

        backed_up, not_found, failed, secrets = result
        assert backed_up == 1
        assert secrets == {"db-credentials", "api-key"}

    def test_backup_secret_does_not_discover_itself(self, tmp_path):
        """Test that backing up Secrets doesn't try to discover secrets"""
        backup_path = str(tmp_path / "backup")

        mock_resource = {
            "metadata": {"name": "my-secret", "namespace": "test-ns"},
            "data": {"password": "encoded-value"},
        }

        mock_resource_obj = MagicMock()
        mock_resource_obj.__getitem__ = lambda self, key: mock_resource[key]
        mock_resource_obj.to_dict.return_value = mock_resource

        mock_client = MagicMock()
        mock_api = MagicMock()
        mock_api.get.return_value = mock_resource_obj
        mock_client.resources.get.return_value = mock_api

        with patch("mas.devops.backup.copyContentsToYamlFile", return_value=True):
            result = backupResources(
                mock_client,
                kind="Secret",
                api_version="v1",
                backup_path=backup_path,
                namespace="test-ns",
                name="my-secret",
            )

        backed_up, not_found, failed, secrets = result
        assert backed_up == 1
        assert secrets == set()  # Should not discover secrets from Secret resources

    def test_backup_write_failure(self, tmp_path):
        """Test handling when writing backup file fails"""
        backup_path = str(tmp_path / "backup")

        mock_resource = {
            "metadata": {"name": "test-resource", "namespace": "test-ns"},
            "spec": {},
        }

        mock_resource_obj = MagicMock()
        mock_resource_obj.__getitem__ = lambda self, key: mock_resource[key]
        mock_resource_obj.to_dict.return_value = mock_resource

        mock_client = MagicMock()
        mock_api = MagicMock()
        mock_api.get.return_value = mock_resource_obj
        mock_client.resources.get.return_value = mock_api

        with patch("mas.devops.backup.copyContentsToYamlFile", return_value=False):
            result = backupResources(
                mock_client,
                kind="ConfigMap",
                api_version="v1",
                backup_path=backup_path,
                namespace="test-ns",
                name="test-resource",
            )

        backed_up, not_found, failed, secrets = result
        assert backed_up == 0
        assert not_found == 0
        assert failed == 1

    def test_backup_api_exception(self):
        """Test handling of general API exceptions"""
        mock_client = MagicMock()
        mock_client.resources.get.side_effect = Exception("API error")

        result = backupResources(
            mock_client,
            kind="ConfigMap",
            api_version="v1",
            backup_path="/tmp/backup",
            namespace="test-ns",
        )

        backed_up, not_found, failed, secrets = result
        assert backed_up == 0
        assert not_found == 0
        assert failed == 1

    def test_backup_mixed_success_and_failure(self, tmp_path):
        """Test backing up multiple resources with mixed success/failure"""
        backup_path = str(tmp_path / "backup")

        mock_resources = [
            {"metadata": {"name": "resource1", "namespace": "test-ns"}, "spec": {}},
            {"metadata": {"name": "resource2", "namespace": "test-ns"}, "spec": {}},
            {"metadata": {"name": "resource3", "namespace": "test-ns"}, "spec": {}},
        ]

        mock_resource_objs = []
        for res in mock_resources:
            mock_obj = MagicMock()
            mock_obj.__getitem__ = lambda self, key, r=res: r[key]
            mock_obj.to_dict.return_value = res
            mock_resource_objs.append(mock_obj)

        mock_response = MagicMock()
        mock_response.items = mock_resource_objs

        mock_client = MagicMock()
        mock_api = MagicMock()
        mock_api.get.return_value = mock_response
        mock_client.resources.get.return_value = mock_api

        with patch("mas.devops.backup.copyContentsToYamlFile") as mock_copy:
            mock_copy.side_effect = [True, True, False]

            result = backupResources(
                mock_client,
                kind="ConfigMap",
                api_version="v1",
                backup_path=backup_path,
                namespace="test-ns",
            )

        backed_up, not_found, failed, secrets = result
        assert backed_up == 2
        assert not_found == 0
        assert failed == 1

    def test_backup_resource_kind_not_found(self):
        """Test when the resource kind itself is not found in the API"""
        mock_client = MagicMock()
        mock_client.resources.get.side_effect = NotFoundError(Mock())

        result = backupResources(
            mock_client,
            kind="NonExistentKind",
            api_version="v1",
            backup_path="/tmp/backup",
            namespace="test-ns",
        )

        backed_up, not_found, failed, secrets = result
        assert backed_up == 0
        assert not_found == 0
        assert failed == 0
