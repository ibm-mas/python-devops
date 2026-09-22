# *****************************************************************************
# Copyright (c) 2025 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************
"""
feature_status.py — Write feature status records into the DevOps MongoDB.

Supports two operations:

  prep          — Verify the MongoDB connection and confirm the expected indexes
                  (instance_config_level, cluster_config_level) exist on the
                  target collection.  Stores db-details for later use in an
                  environment variable so they do not need to be repeated on
                  every status-update call.

  status_update — Upsert a feature status document into
                  ``mas_devops.feature_status``.

Collection: ``mas_devops.feature_status``

Document schema (mirrors the CIS allowlist status tracking design):

  {
    "_id": <ObjectId>,
    "schema_version": 1,
    "region": str,
    "instance_id": str,
    "account": str,
    "cluster": str,
    "subscription_id": str,
    "type": str,                    # e.g. "allow-list"
    "feature_details": dict,        # type-specific payload
    "status": str,                  # REQUESTED | IN_PROGRESS | ACTIVE | ERROR
    "status_details": dict,         # message, error_code, error_source, …
    "deployment_start": datetime,
    "deployment_end":   datetime | None,
    "created_at": datetime,
    "updated_at": datetime,
  }

Indexes expected on the collection
  • ``instance_config_level`` — compound: region + instance_id + account
  • ``cluster_config_level``  — compound: region + cluster + account
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLLECTION = "feature_status"
DATABASE = "mas_devops"

# Status enum values (matches the CIS allowlist lifecycle)
STATUS_REQUESTED = "REQUESTED"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_ACTIVE = "ACTIVE"
STATUS_ERROR = "ERROR"

VALID_STATUSES = {STATUS_REQUESTED, STATUS_IN_PROGRESS, STATUS_ACTIVE, STATUS_ERROR}

# Required index names that must exist on the collection.
REQUIRED_INDEX_NAMES = {"instance_config_level", "cluster_config_level"}

# ---------------------------------------------------------------------------
# Per-type feature_details validators
# ---------------------------------------------------------------------------

# Each key maps to the set of field names that MUST be present in feature_details
# when --type matches that key.
_FEATURE_DETAILS_REQUIRED_FIELDS: dict[str, set[str]] = {
    "allow-list": {"ips"},
}


def validate_feature_details(feature_type: str, feature_details: dict) -> None:
    """Validate that *feature_details* contains the required keys for *feature_type*.

    Raises:
        ValueError: if required keys are missing or feature_details is not a dict.
    """
    if not isinstance(feature_details, dict):
        raise ValueError(f"feature_details must be a JSON object, got {type(feature_details).__name__}")

    required = _FEATURE_DETAILS_REQUIRED_FIELDS.get(feature_type)
    if required is None:
        # Unknown type — no field-level validation, but emit a warning.
        logger.warning("No feature_details validation rules defined for type '%s'", feature_type)
        return

    missing = required - set(feature_details.keys())
    if missing:
        raise ValueError(f"feature_details is missing required field(s) for type '{feature_type}': {sorted(missing)}")


# ---------------------------------------------------------------------------
# MongoDB helpers
# ---------------------------------------------------------------------------


def _get_client(mongo_url: str, credentials: Optional[dict] = None):
    """Return a pymongo MongoClient for *mongo_url*.

    Credentials dict may contain ``username`` and ``password`` keys.
    If the URL already embeds credentials they take precedence.
    """
    try:
        from pymongo import MongoClient  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pymongo is required. Install it with: pip install pymongo") from exc

    kwargs: dict[str, Any] = {"serverSelectionTimeoutMS": 10_000}
    if credentials:
        if "username" in credentials:
            kwargs["username"] = credentials["username"]
        if "password" in credentials:
            kwargs["password"] = credentials["password"]
        if "authSource" in credentials:
            kwargs["authSource"] = credentials["authSource"]
        if "tls" in credentials:
            kwargs["tls"] = credentials["tls"]

    return MongoClient(mongo_url, **kwargs)


def verify_connection_and_indexes(mongo_url: str, credentials: Optional[dict] = None) -> list[str]:
    """Connect to MongoDB and check that the expected indexes exist.

    Returns a list of warning messages for any missing indexes.
    Raises on connection failure.
    """
    client = _get_client(mongo_url, credentials)
    try:
        # Ping — will raise if the server is unreachable.
        client.admin.command("ping")
        logger.info("MongoDB connection OK: %s", _redact_url(mongo_url))

        db = client[DATABASE]
        collection = db[COLLECTION]

        # Retrieve existing index names.
        existing_index_names = {info["name"] for info in collection.list_indexes()}

        warnings = []
        for expected in REQUIRED_INDEX_NAMES:
            if expected not in existing_index_names:
                warnings.append(
                    f"Index '{expected}' not found on {DATABASE}.{COLLECTION}. " f"Run the index-creation script or use 'prep' with --create-indexes."
                )
        return warnings
    finally:
        client.close()


def create_indexes(mongo_url: str, credentials: Optional[dict] = None) -> None:
    """Create the required indexes on the feature_status collection if they do not exist."""
    try:
        from pymongo import ASCENDING  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pymongo is required. Install it with: pip install pymongo") from exc

    client = _get_client(mongo_url, credentials)
    try:
        db = client[DATABASE]
        collection = db[COLLECTION]

        collection.create_index(
            [("region", ASCENDING), ("instance_id", ASCENDING), ("account", ASCENDING)],
            name="instance_config_level",
            background=True,
        )
        logger.info("Index 'instance_config_level' ensured on %s.%s", DATABASE, COLLECTION)

        collection.create_index(
            [("region", ASCENDING), ("cluster", ASCENDING), ("account", ASCENDING)],
            name="cluster_config_level",
            background=True,
        )
        logger.info("Index 'cluster_config_level' ensured on %s.%s", DATABASE, COLLECTION)
    finally:
        client.close()


def upsert_feature_status(
    mongo_url: str,
    *,
    region: str,
    instance_id: str,
    account: str,
    cluster: str,
    subscription_id: str,
    feature_type: str,
    feature_details: dict,
    status: str,
    status_details: dict,
    deployment_start: Optional[datetime] = None,
    deployment_end: Optional[datetime] = None,
    created_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
    credentials: Optional[dict] = None,
) -> str:
    """Upsert a feature status document.  Returns the upserted / matched document ID as a string.

    The upsert key is ``(region, instance_id, account, cluster, type)``.
    On insert ``created_at`` is set; ``updated_at`` is always refreshed.
    """
    try:
        from pymongo import ReturnDocument  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pymongo is required. Install it with: pip install pymongo") from exc

    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of {sorted(VALID_STATUSES)}")

    validate_feature_details(feature_type, feature_details)

    now = datetime.now(timezone.utc)
    deployment_start = deployment_start or now
    updated_at = updated_at or now
    created_at = created_at or now

    filter_doc = {
        "region": region,
        "instance_id": instance_id,
        "account": account,
        "cluster": cluster,
        "type": feature_type,
    }

    update_doc = {
        "$set": {
            "subscription_id": subscription_id,
            "feature_details": feature_details,
            "status": status,
            "status_details": status_details,
            "deployment_start": deployment_start,
            "deployment_end": deployment_end,
            "updated_at": updated_at,
            "schema_version": 1,
        },
        "$setOnInsert": {
            "created_at": created_at,
        },
    }

    client = _get_client(mongo_url, credentials)
    try:
        db = client[DATABASE]
        collection = db[COLLECTION]
        result = collection.find_one_and_update(
            filter_doc,
            update_doc,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        doc_id = str(result["_id"])
        logger.info(
            "Feature status upserted [%s / %s / %s] status=%s id=%s",
            account,
            instance_id,
            feature_type,
            status,
            doc_id,
        )
        return doc_id
    finally:
        client.close()


def get_feature_status_by_id(mongo_url: str, doc_id: str, credentials: Optional[dict] = None) -> Optional[dict]:
    """Fetch a single feature status document by its ObjectId string.

    Args:
        mongo_url (str): MongoDB connection URL.
        doc_id (str): Hex string ObjectId of the document to retrieve.
        credentials (dict, optional): Optional credential overrides. Defaults to None.

    Returns:
        dict: The document with ``_id`` serialised to a string, or None if not found.

    Raises:
        ValueError: If *doc_id* is not a valid 24-character hex ObjectId.
        pymongo.errors.ConnectionFailure: If the MongoDB server is unreachable.
    """
    try:
        from bson import ObjectId
        from bson.errors import InvalidId
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pymongo is required. Install it with: pip install pymongo") from exc

    try:
        oid = ObjectId(doc_id)
    except InvalidId:
        raise ValueError(f"'{doc_id}' is not a valid ObjectId (expected a 24-character hex string)")

    client = _get_client(mongo_url, credentials)
    try:
        doc = client[DATABASE][COLLECTION].find_one({"_id": oid})
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return doc
    finally:
        client.close()


# ---------------------------------------------------------------------------
# URL redaction helper (keeps passwords out of logs)
# ---------------------------------------------------------------------------


def _redact_url(url: str) -> str:
    """Replace the password component of a MongoDB connection URI with *****."""
    import re

    return re.sub(r"(mongodb(?:\+srv)?://[^:]+:)[^@]+(@)", r"\1*****\2", url)
