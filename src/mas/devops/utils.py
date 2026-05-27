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


def extractBaseVersion(version: str) -> str:
    """
    Extract base version (major.minor) from a version string.

    This function normalizes version strings by removing pre-release identifiers,
    build metadata, and patch versions to return just the major.minor version.
    This is used for RBAC resource selection, as RBAC resources are organized
    by major.minor version (e.g., 9.2/, 9.3/).

    Examples:
        "9.2.0" -> "9.2"
        "9.2.0-pre.stable+21734" -> "9.2"
        "9.2.x-dev" -> "9.2"
        "9.2.x" -> "9.2"

    Args:
        version (str): Version string to parse.

    Returns:
        str: Base version (major.minor), or empty string if version is None/empty.
    """
    if not version:
        return ""

    # Remove pre-release metadata (everything after first "-")
    # Then remove build metadata (everything after first "+")
    # Example: "9.2.0-pre.stable+21734" -> "9.2.0"
    baseVersion = version.split("-")[0].split("+")[0]

    # Remove .x suffix if present
    if '.x' in baseVersion:
        baseVersion = baseVersion.replace(".x", "")

    # Extract major.minor (first two parts)
    # Split "9.2.0" by "." -> ["9", "2", "0"]
    # Take first two: "9" and "2" -> "9.2"
    parts = baseVersion.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"

    return baseVersion


def isPreReleaseVersion(version: str) -> bool:
    """
    Check if a version string represents a pre-release version.

    Pre-release versions contain "-pre" in the version string, such as
    "9.2.0-pre.stable+21734" or "9.2.0-pre.m1dev86".

    Args:
        version (str): Version string to check (e.g., "9.2.0-pre.stable+21734").

    Returns:
        bool: True if the version is a pre-release, False otherwise.
              Returns False if version is None or empty.
    """
    return "-pre" in version if version else False
