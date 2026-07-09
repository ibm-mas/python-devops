# *****************************************************************************
# Copyright (c) 2024, 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

import os
import pytest

from mas.devops.pre_install import (
    _validate_selected_apps,
    _get_selected_operator_dirs,
    _should_apply_preinstall_mas_rbac_file,
    _resolve_rbac_version,
    _collect_preinstall_mas_rbac_files_from_source,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def make_rbac_dir(tmp_path):
    """Create x.y subdirs under tmp_path/rbac and return the rbac path."""
    rbac = tmp_path / "rbac"
    rbac.mkdir()

    def _make(*versions):
        for v in versions:
            (rbac / v).mkdir()
        return str(rbac)

    return _make


@pytest.fixture()
def make_operator_tree(tmp_path):
    """Build a minimal operators source tree and return its root path.

    Usage:
        root = make_operator_tree({
            "ibm-mas-manage": {"9.2": ["cluster-role-foo.yaml", "role-non-essential-bar.yaml"]},
        })
    """
    def _make(operators: dict) -> str:
        for operatorName, versions in operators.items():
            for version, files in versions.items():
                versionDir = tmp_path / operatorName / "rbac" / version
                versionDir.mkdir(parents=True)
                for fileName in files:
                    (versionDir / fileName).write_text(f"# {fileName}\n")
        return str(tmp_path)

    return _make


# ===========================================================================
# _validate_selected_apps
# ===========================================================================

def test_validate_selected_apps_none_returns_empty():
    assert _validate_selected_apps(None) == set()


def test_validate_selected_apps_empty_list_returns_empty():
    assert _validate_selected_apps([]) == set()


def test_validate_selected_apps_valid_single():
    assert _validate_selected_apps(["manage"]) == {"manage"}


def test_validate_selected_apps_valid_multiple():
    assert _validate_selected_apps(["manage", "iot", "monitor"]) == {"manage", "iot", "monitor"}


def test_validate_selected_apps_all_valid():
    all_apps = ["core", "aiservice", "arcgis", "facilities", "iot", "manage", "monitor", "optimizer", "predict", "visualinspection"]
    assert _validate_selected_apps(all_apps) == set(all_apps)


def test_validate_selected_apps_invalid_raises():
    with pytest.raises(ValueError, match="Unsupported selected app: unknown"):
        _validate_selected_apps(["manage", "unknown"])


def test_validate_selected_apps_deduplicates():
    assert _validate_selected_apps(["manage", "manage"]) == {"manage"}


# ===========================================================================
# _get_selected_operator_dirs
# ===========================================================================

def test_get_selected_operator_dirs_core_maps_to_ibm_mas():
    assert _get_selected_operator_dirs({"core"}) == {"ibm-mas"}


def test_get_selected_operator_dirs_app_maps_correctly():
    assert _get_selected_operator_dirs({"manage"}) == {"ibm-mas-manage"}
    assert _get_selected_operator_dirs({"iot"}) == {"ibm-mas-iot"}
    assert _get_selected_operator_dirs({"monitor"}) == {"ibm-mas-monitor"}
    assert _get_selected_operator_dirs({"optimizer"}) == {"ibm-mas-optimizer"}
    assert _get_selected_operator_dirs({"predict"}) == {"ibm-mas-predict"}
    assert _get_selected_operator_dirs({"visualinspection"}) == {"ibm-mas-visualinspection"}
    assert _get_selected_operator_dirs({"arcgis"}) == {"ibm-mas-arcgis"}
    assert _get_selected_operator_dirs({"facilities"}) == {"ibm-mas-facilities"}
    assert _get_selected_operator_dirs({"aiservice"}) == {"ibm-aiservice"}


def test_get_selected_operator_dirs_multiple():
    result = _get_selected_operator_dirs({"core", "manage", "iot"})
    assert result == {"ibm-mas", "ibm-mas-manage", "ibm-mas-iot"}


# ===========================================================================
# _should_apply_preinstall_mas_rbac_file
# ===========================================================================

class TestShouldApplyClusterMode:
    def test_cluster_role_yaml_applied(self):
        assert _should_apply_preinstall_mas_rbac_file("cluster-role-foo.yaml", "cluster") is True

    def test_cluster_role_yml_applied(self):
        assert _should_apply_preinstall_mas_rbac_file("cluster-role-foo.yml", "cluster") is True

    def test_cluster_role_uppercase_applied(self):
        assert _should_apply_preinstall_mas_rbac_file("CLUSTER-ROLE-FOO.YAML", "cluster") is True

    def test_role_non_essential_skipped_in_cluster_mode(self):
        assert _should_apply_preinstall_mas_rbac_file("role-non-essential-foo.yaml", "cluster") is False

    def test_kustomization_skipped_in_cluster_mode(self):
        assert _should_apply_preinstall_mas_rbac_file("kustomization.yaml", "cluster") is False

    def test_non_yaml_skipped_in_cluster_mode(self):
        assert _should_apply_preinstall_mas_rbac_file("cluster-role-foo.json", "cluster") is False

    def test_random_yaml_skipped_in_cluster_mode(self):
        assert _should_apply_preinstall_mas_rbac_file("some-other-file.yaml", "cluster") is False


class TestShouldApplyNamespacedMode:
    def test_role_non_essential_yaml_applied(self):
        assert _should_apply_preinstall_mas_rbac_file("role-non-essential-foo.yaml", "namespaced") is True

    def test_role_non_essential_yml_applied(self):
        assert _should_apply_preinstall_mas_rbac_file("role-non-essential-foo.yml", "namespaced") is True

    def test_role_non_essential_uppercase_applied(self):
        assert _should_apply_preinstall_mas_rbac_file("ROLE-NON-ESSENTIAL-FOO.YAML", "namespaced") is True

    def test_cluster_role_skipped_in_namespaced_mode(self):
        assert _should_apply_preinstall_mas_rbac_file("cluster-role-foo.yaml", "namespaced") is False

    def test_kustomization_skipped_in_namespaced_mode(self):
        assert _should_apply_preinstall_mas_rbac_file("kustomization.yaml", "namespaced") is False

    def test_non_yaml_skipped_in_namespaced_mode(self):
        assert _should_apply_preinstall_mas_rbac_file("role-non-essential-foo.json", "namespaced") is False

    def test_path_with_directories_uses_basename(self):
        assert _should_apply_preinstall_mas_rbac_file("/some/path/cluster-role-foo.yaml", "cluster") is True
        assert _should_apply_preinstall_mas_rbac_file("/some/path/role-non-essential-foo.yaml", "namespaced") is True


class TestShouldApplyMinimalMode:
    def test_nothing_applied_in_unknown_mode(self):
        assert _should_apply_preinstall_mas_rbac_file("cluster-role-foo.yaml", "minimal") is False
        assert _should_apply_preinstall_mas_rbac_file("role-non-essential-foo.yaml", "minimal") is False


# ===========================================================================
# _resolve_rbac_version
# ===========================================================================

class TestResolveRbacVersion:
    def test_exact_match(self, make_rbac_dir):
        """Running 9.2, 9.2 dir exists — picks 9.2."""
        d = make_rbac_dir("9.2")
        assert _resolve_rbac_version(d, "9.2") == "9.2"

    def test_fallback_to_lower(self, make_rbac_dir):
        """Running 9.4, only 9.2 dir exists — falls back to 9.2."""
        d = make_rbac_dir("9.2")
        assert _resolve_rbac_version(d, "9.4") == "9.2"

    def test_picks_highest_lower(self, make_rbac_dir):
        """Running 9.6, dirs 9.2 and 9.5 exist — picks 9.5 not 9.2."""
        d = make_rbac_dir("9.2", "9.5")
        assert _resolve_rbac_version(d, "9.6") == "9.5"

    def test_skips_future_dirs(self, make_rbac_dir):
        """Running 9.4, dirs 9.2 and 9.5 exist — 9.5 is too new, picks 9.2."""
        d = make_rbac_dir("9.2", "9.5")
        assert _resolve_rbac_version(d, "9.4") == "9.2"

    def test_exact_match_with_multiple_dirs(self, make_rbac_dir):
        """Running 9.5, dirs 9.2 and 9.5 both exist — picks 9.5."""
        d = make_rbac_dir("9.2", "9.5")
        assert _resolve_rbac_version(d, "9.5") == "9.5"

    def test_semantic_order_9_10_greater_than_9_9(self, make_rbac_dir):
        """9.10 > 9.9 semantically — must not be treated as 9.1."""
        d = make_rbac_dir("9.2", "9.9", "9.10")
        assert _resolve_rbac_version(d, "9.10") == "9.10"

    def test_semantic_order_skips_9_10_when_running_9_9(self, make_rbac_dir):
        """Running 9.9 with 9.10 on disk — 9.10 correctly skipped."""
        d = make_rbac_dir("9.2", "9.9", "9.10")
        assert _resolve_rbac_version(d, "9.9") == "9.9"

    def test_version_below_all_available_returns_none(self, make_rbac_dir):
        """Running 9.1, only 9.2 dir exists — nothing qualifies."""
        d = make_rbac_dir("9.2")
        assert _resolve_rbac_version(d, "9.1") is None

    def test_empty_directory_returns_none(self, make_rbac_dir):
        """No x.y subdirectories at all — returns None."""
        d = make_rbac_dir()
        assert _resolve_rbac_version(d, "9.4") is None

    def test_non_version_dirs_ignored(self, make_rbac_dir):
        """Directories like common/ and latest/ are silently ignored."""
        rbac = make_rbac_dir("9.2")
        os.makedirs(os.path.join(rbac, "common"))
        os.makedirs(os.path.join(rbac, "latest"))
        assert _resolve_rbac_version(rbac, "9.4") == "9.2"

    def test_three_part_version_dirs_ignored(self, make_rbac_dir):
        """Directories like 9.2.1 don't match x.y pattern — ignored."""
        rbac = make_rbac_dir("9.2")
        os.makedirs(os.path.join(rbac, "9.2.1"))
        assert _resolve_rbac_version(rbac, "9.4") == "9.2"

    def test_missing_rbac_dir_returns_none(self, tmp_path):
        """rbacDir does not exist at all — returns None gracefully."""
        assert _resolve_rbac_version(str(tmp_path / "does-not-exist"), "9.4") is None

    def test_result_independent_of_filesystem_order(self, make_rbac_dir):
        """listdir order is non-deterministic — result must always be correct."""
        d = make_rbac_dir("9.5", "9.2", "9.3")
        assert _resolve_rbac_version(d, "9.6") == "9.5"
        assert _resolve_rbac_version(d, "9.3") == "9.3"
        assert _resolve_rbac_version(d, "9.2") == "9.2"
        assert _resolve_rbac_version(d, "9.4") == "9.3"


# ===========================================================================
# _collect_preinstall_mas_rbac_files_from_source
# ===========================================================================

class TestCollectPreinstallMasRbacFilesFromSource:
    def test_missing_source_root_returns_empty(self, tmp_path):
        result = _collect_preinstall_mas_rbac_files_from_source(
            sourceOperatorsRoot=str(tmp_path / "missing"),
            masVersion="9.4",
            adminMode="cluster",
        )
        assert result == []

    def test_exact_version_match_cluster_mode(self, make_operator_tree):
        root = make_operator_tree({
            "ibm-mas-manage": {"9.2": ["cluster-role-manage.yaml", "role-non-essential-manage.yaml"]},
        })
        result = _collect_preinstall_mas_rbac_files_from_source(
            sourceOperatorsRoot=root,
            masVersion="9.2",
            adminMode="cluster",
        )
        assert len(result) == 1
        assert os.path.basename(result[0]) == "cluster-role-manage.yaml"

    def test_exact_version_match_namespaced_mode(self, make_operator_tree):
        root = make_operator_tree({
            "ibm-mas-manage": {"9.2": ["cluster-role-manage.yaml", "role-non-essential-manage.yaml"]},
        })
        result = _collect_preinstall_mas_rbac_files_from_source(
            sourceOperatorsRoot=root,
            masVersion="9.2",
            adminMode="namespaced",
        )
        assert len(result) == 1
        assert os.path.basename(result[0]) == "role-non-essential-manage.yaml"

    def test_version_fallback_uses_lower_dir(self, make_operator_tree):
        """Running 9.4, only 9.2 dir exists — resolves to 9.2."""
        root = make_operator_tree({
            "ibm-mas-manage": {"9.2": ["cluster-role-manage.yaml"]},
        })
        result = _collect_preinstall_mas_rbac_files_from_source(
            sourceOperatorsRoot=root,
            masVersion="9.4",
            adminMode="cluster",
        )
        assert len(result) == 1
        # full path must include the resolved version directory name
        assert os.path.join("rbac", "9.2") in result[0]

    def test_operator_with_no_rbac_dir_skipped(self, make_operator_tree):
        """Operator directory exists but has no rbac/ subdir — skipped."""
        root = make_operator_tree({
            "ibm-mas-manage": {"9.2": ["cluster-role-manage.yaml"]},
        })
        # add an operator dir with no rbac subdir
        os.makedirs(os.path.join(root, "ibm-mas-iot"))
        result = _collect_preinstall_mas_rbac_files_from_source(
            sourceOperatorsRoot=root,
            masVersion="9.2",
            adminMode="cluster",
            operatorNames={"ibm-mas-manage", "ibm-mas-iot"},
        )
        assert len(result) == 1
        assert "ibm-mas-manage" in result[0]

    def test_version_too_old_skips_operator(self, make_operator_tree):
        """Running 9.1, only 9.2 dir exists — operator is skipped entirely."""
        root = make_operator_tree({
            "ibm-mas-manage": {"9.2": ["cluster-role-manage.yaml"]},
        })
        result = _collect_preinstall_mas_rbac_files_from_source(
            sourceOperatorsRoot=root,
            masVersion="9.1",
            adminMode="cluster",
        )
        assert result == []

    def test_operator_names_filter(self, make_operator_tree):
        """Only operators in operatorNames are processed."""
        root = make_operator_tree({
            "ibm-mas-manage": {"9.2": ["cluster-role-manage.yaml"]},
            "ibm-mas-iot": {"9.2": ["cluster-role-iot.yaml"]},
        })
        result = _collect_preinstall_mas_rbac_files_from_source(
            sourceOperatorsRoot=root,
            masVersion="9.2",
            adminMode="cluster",
            operatorNames={"ibm-mas-manage"},
        )
        assert len(result) == 1
        assert "ibm-mas-manage" in result[0]

    def test_multiple_operators_collected_in_order(self, make_operator_tree):
        """Files from multiple operators are collected, operators sorted."""
        root = make_operator_tree({
            "ibm-mas-manage": {"9.2": ["cluster-role-manage.yaml"]},
            "ibm-mas-iot": {"9.2": ["cluster-role-iot.yaml"]},
        })
        result = _collect_preinstall_mas_rbac_files_from_source(
            sourceOperatorsRoot=root,
            masVersion="9.2",
            adminMode="cluster",
        )
        assert len(result) == 2
        # sorted by operator name — iot before manage alphabetically
        assert "ibm-mas-iot" in result[0]
        assert "ibm-mas-manage" in result[1]

    def test_kustomization_file_excluded(self, make_operator_tree):
        """kustomization.yaml is always excluded regardless of adminMode."""
        root = make_operator_tree({
            "ibm-mas-manage": {"9.2": ["cluster-role-manage.yaml", "kustomization.yaml"]},
        })
        result = _collect_preinstall_mas_rbac_files_from_source(
            sourceOperatorsRoot=root,
            masVersion="9.2",
            adminMode="cluster",
        )
        # Check basenames only — the tmp_path directory itself is named after
        # the test function and contains "kustomization" in its path string.
        result_basenames = [os.path.basename(f) for f in result]
        assert "kustomization.yaml" not in result_basenames
        assert "cluster-role-manage.yaml" in result_basenames
