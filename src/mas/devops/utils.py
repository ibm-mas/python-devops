"""
Utility functions for version comparison and other common operations.

This module provides semantic version comparison utilities with custom handling
for pre-release versions and wildcard version strings.
"""

import semver


def isVersionBefore(_compare_to_version, _current_version):
    """
    Check if the current version is before (older than) the comparison version.

    This function performs a modified semantic version comparison where pre-release
    versions are treated as equal to their base release version. For example,
    '8.6.0-pre.m1dev86' is normalized to '8.6.0' before comparison. Wildcard versions
    like '8.6.x' are converted to '8.6.0'.

    Args:
        _compare_to_version (str): The version to compare against (e.g., "8.6.0").
        _current_version (str): The current version to check (e.g., "8.5.0" or "8.6.0-pre.m1dev86").
                               Can be None, in which case False is returned.

    Returns:
        bool: True if current_version < compare_to_version, False otherwise.
              Returns False if _current_version is None.

    Note:
        This differs from strict semantic versioning where pre-release versions
        are considered less than their base version.
    """
    if _current_version is None:
        print("Version is not informed. Returning False")
        return False

    strippedVersion = _current_version.split("-")[0]
    if '.x' in strippedVersion:
        strippedVersion = strippedVersion.replace('.x', '.0')
    current_version = semver.VersionInfo.parse(strippedVersion)
    compareToVersion = semver.VersionInfo.parse(_compare_to_version)
    return current_version.compare(compareToVersion) < 0


def isVersionEqualOrAfter(_compare_to_version, _current_version):
    """
    Check if the current version is equal to or after (newer than) the comparison version.

    This function performs a modified semantic version comparison where pre-release
    versions are treated as equal to their base release version. For example,
    '8.6.0-pre.m1dev86' is normalized to '8.6.0' before comparison. Wildcard versions
    like '8.6.x' are converted to '8.6.0'.

    Args:
        _compare_to_version (str): The version to compare against (e.g., "8.6.0").
        _current_version (str): The current version to check (e.g., "8.7.0" or "8.6.0-pre.m1dev86").
                               Can be None, in which case False is returned.

    Returns:
        bool: True if current_version >= compare_to_version, False otherwise.
              Returns False if _current_version is None.

    Note:
        This differs from strict semantic versioning where pre-release versions
        are considered less than their base version.
    """
    if _current_version is None:
        print("Version is not informed. Returning False")
        return False

    strippedVersion = _current_version.split("-")[0]
    if '.x' in strippedVersion:
        strippedVersion = strippedVersion.replace('.x', '.0')
    current_version = semver.VersionInfo.parse(strippedVersion)
    compareToVersion = semver.VersionInfo.parse(_compare_to_version)
    return current_version.compare(compareToVersion) >= 0
