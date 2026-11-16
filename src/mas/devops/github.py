# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

"""GitHub Checks API helpers for FVT result reporting.

Provides createCheckRun() and updateCheckRun() to post check run status
against specific commits on github.ibm.com, using a GitHub App for auth.

Authentication is handled automatically. Set GITHUB_APP_PRIVATE_KEY in the
environment; an installation token is fetched, cached, and refreshed
transparently.

Environment variables:
    GITHUB_APP_PRIVATE_KEY      (required) PEM-encoded RSA private key.
    GITHUB_API_BASE             (optional) Override API base URL.
                                Defaults to https://github.ibm.com/api/v3
    GITHUB_APP_ID               (optional) Override app ID. Defaults to 6035.
    GITHUB_APP_INSTALLATION_ID  (optional) Skip installation lookup.
"""

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)

_GITHUB_API_BASE = os.environ.get("GITHUB_API_BASE", "https://github.ibm.com/api/v3")
_GITHUB_APP_ID = os.environ.get("GITHUB_APP_ID", "6035")


# ---------------------------------------------------------------------------
# Token cache
# ---------------------------------------------------------------------------
@dataclass
class _TokenCache:
    token: str = ""
    expiresAt: float = field(default_factory=float)


_tokenCache: dict[str, _TokenCache] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _buildJwt(privateKeyPem: str) -> str:
    """Build a signed RS256 JWT to authenticate as the GitHub App."""
    key = serialization.load_pem_private_key(privateKeyPem.encode(), password=None)
    now = int(time.time())
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"iat": now - 60, "exp": now + 540, "iss": _GITHUB_APP_ID}).encode()).rstrip(b"=")
    message = header + b"." + payload
    sig = base64.urlsafe_b64encode(key.sign(message, padding.PKCS1v15(), hashes.SHA256())).rstrip(b"=")
    return (message + b"." + sig).decode()


def _apiRequest(method: str, url: str, token: str, payload: dict | None = None, isJwt: bool = False) -> dict:
    """Send an authenticated request to the GitHub API."""
    data = json.dumps(payload).encode() if payload else None
    authScheme = "Bearer" if isJwt else "token"
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"{authScheme} {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GHE API {method} {url} → {e.code}: {e.read().decode(errors='replace')}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"GHE API request failed: {e.reason}") from e


def _getInstallationToken(org: str) -> str:
    """Return a valid installation token for *org*, refreshing when near expiry."""
    cache = _tokenCache.get(org)
    if cache and cache.token and time.time() < cache.expiresAt - 60:
        return cache.token

    privateKeyPem = os.environ.get("GITHUB_APP_PRIVATE_KEY")
    if not privateKeyPem:
        raise RuntimeError("GITHUB_APP_PRIVATE_KEY environment variable is not set")

    jwt = _buildJwt(privateKeyPem)

    # Resolve installation ID for this org (or use explicit override)
    installationId = os.environ.get("GITHUB_APP_INSTALLATION_ID")
    if not installationId:
        installations = _apiRequest("GET", f"{_GITHUB_API_BASE}/app/installations", jwt, isJwt=True)
        for inst in installations:
            if inst.get("account", {}).get("login", "").lower() == org.lower():
                installationId = str(inst["id"])
                break
        if not installationId:
            raise RuntimeError(f"No GHE App installation found for org '{org}'")

    body = _apiRequest("POST", f"{_GITHUB_API_BASE}/app/installations/{installationId}/access_tokens", jwt, payload={}, isJwt=True)
    token = body.get("token")
    if not token:
        raise RuntimeError(f"No token in GHE access_tokens response: {body}")

    _tokenCache[org] = _TokenCache(token=token, expiresAt=time.time() + 3600)
    logger.debug("Fetched GHE installation token for org=%s", org)
    return token


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def createCheckRun(name: str, repoSlug: str, commitSha: str, detailsUrl: str = "") -> int:
    """Create a GitHub Check Run in 'in_progress' state. Returns the check run ID."""
    org = repoSlug.split("/")[0]
    appToken = _getInstallationToken(org)
    isoNow = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload: dict = {"name": name, "head_sha": commitSha, "status": "in_progress", "started_at": isoNow}
    if detailsUrl:
        payload["details_url"] = detailsUrl
    response = _apiRequest("POST", f"{_GITHUB_API_BASE}/repos/{repoSlug}/check-runs", appToken, payload)
    checkRunId = response.get("id")
    if not checkRunId:
        raise RuntimeError(f"Failed to create check run '{name}': {response}")
    logger.debug("Created check run id=%s for %s@%s", checkRunId, repoSlug, commitSha[:8])
    return checkRunId


def updateCheckRun(checkRunId: int, repoSlug: str, conclusion: str, detailsUrl: str = "", outputTitle: str = "", outputSummary: str = "") -> None:
    """Complete an existing GitHub Check Run with the given conclusion."""
    org = repoSlug.split("/")[0]
    appToken = _getInstallationToken(org)
    isoNow = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload: dict = {"status": "completed", "conclusion": conclusion, "completed_at": isoNow}
    if detailsUrl:
        payload["details_url"] = detailsUrl
    if outputTitle and outputSummary:
        payload["output"] = {"title": outputTitle, "summary": outputSummary}
    _apiRequest("PATCH", f"{_GITHUB_API_BASE}/repos/{repoSlug}/check-runs/{checkRunId}", appToken, payload)
    logger.debug("Updated check run id=%s conclusion=%s", checkRunId, conclusion)


def findCheckRun(name: str, repoSlug: str, commitSha: str) -> int | None:
    """Return the ID of the most recent existing check run matching name+commit, or None.

    Used to upsert — update an existing check run rather than creating a duplicate.
    """
    org = repoSlug.split("/")[0]
    appToken = _getInstallationToken(org)
    url = f"{_GITHUB_API_BASE}/repos/{repoSlug}/commits/{commitSha}/check-runs"
    response = _apiRequest("GET", url, appToken)
    for run in response.get("check_runs", []):
        if run.get("name") == name:
            logger.debug("Found existing check run id=%s name=%s", run["id"], name)
            return run["id"]
    return None
