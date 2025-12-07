import semver


def isVersionBefore(_compare_to_version, _current_version):
    """
    The method does a modified semantic version comparison,
    as we want to treat any pre-release as == to the real release
    but in strict semantic versioning it is <
    ie. '8.6.0-pre.m1dev86' is converted to '8.6.0'
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
    The method does a modified semantic version comparison,
    as we want to treat any pre-release as == to the real release
    but in strict semantic versioning it is <
    ie. '8.6.0-pre.m1dev86' is converted to '8.6.0'
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
