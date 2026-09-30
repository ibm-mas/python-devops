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

Database:    mas_devops
Collections:
  instance_level_config — one document per (tenant_id × subscription_id ×
                           account × region × cluster × instance).
                           Feature entries are embedded in instance_level_features[].
                           Used when --instance-id is supplied.

  cluster_level_config  — one document per (tenant_id × account × region × cluster).
                           Feature entries are embedded in cluster_level_features[].
                           Used when --instance-id is omitted.

Document schema — instance_level_config top-level:

  {
    "_id":          <ObjectId>,
    "tenant_id":    str,
    "subscription_id": str,
    "account":      str,
    "region":       str,
    "cluster":      str,
    "instance":     str,
    "instance_level_features": [
      {
        "type":            str,       # e.g. "allow-list"
        "feature_details": dict,      # type-specific payload
        "status":          str,       # REQUESTED | IN_PROGRESS | ACTIVE | ERROR
        "status_details":  dict,      # message, error_code, error_source, …
        "deployment_start": str,      # ISO-8601
        "deployment_end":   str|None, # ISO-8601
        "source":          str,       # "ansible_devops"
        "created_at":      datetime,
        "updated_at":      datetime,
      },
      …
    ],
    "created_at": datetime,
    "updated_at": datetime,
  }

Document schema — cluster_level_config top-level:

  {
    "_id":        <ObjectId>,
    "tenant_id":  str,
    "account":    str,
    "region":     str,
    "cluster":    str,
    "cluster_level_features": [
      {
        "type":            str,
        "feature_details": dict,
        "status":          str,
        "status_details":  dict,
        "deployment_start": str,
        "deployment_end":   str|None,
        "source":          str,
        "created_at":      datetime,
        "updated_at":      datetime,
      },
      …
    ],
    "created_at": datetime,
    "updated_at": datetime,
  }
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATABASE = "mas_devops"
COLLECTION_INSTANCE = "instance_level_config"
COLLECTION_CLUSTER = "cluster_level_config"

# Source tag written by this CLI tool into every feature entry.
FEATURE_SOURCE = "ansible_devops"

# Status enum values
STATUS_REQUESTED = "REQUESTED"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_ACTIVE = "ACTIVE"
STATUS_ERROR = "ERROR"

VALID_STATUSES = {STATUS_REQUESTED, STATUS_IN_PROGRESS, STATUS_ACTIVE, STATUS_ERROR}

# Feature-level constants
INSTANCE_LEVEL = "INSTANCE_LEVEL"
CLUSTER_LEVEL = "CLUSTER_LEVEL"

# ---------------------------------------------------------------------------
# Feature type → level map
#
# Declares which collection a feature type belongs to.  Add new feature types
# here; the routing logic in the CLI and the library functions will pick it up
# automatically.
#
# INSTANCE_LEVEL → mas_devops.instance_level_config  (requires --instance-id)
# CLUSTER_LEVEL  → mas_devops.cluster_level_config   (no --instance-id needed)
# ---------------------------------------------------------------------------

FEATURE_LEVEL_MAP: dict[str, str] = {
    "allow-list": INSTANCE_LEVEL,
}


def get_feature_level(feature_type: str) -> str:
    """Return the level constant (INSTANCE_LEVEL or CLUSTER_LEVEL) for *feature_type*.

    Raises:
        ValueError: if *feature_type* is not registered in FEATURE_LEVEL_MAP.
    """
    level = FEATURE_LEVEL_MAP.get(feature_type)
    if level is None:
        known = sorted(FEATURE_LEVEL_MAP.keys())
        raise ValueError(f"Unknown feature type '{feature_type}'. " f"Known types: {known}. " f"Add it to FEATURE_LEVEL_MAP in feature_status.py.")
    return level


# ---------------------------------------------------------------------------
# Per-type feature_details validators
# ---------------------------------------------------------------------------

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
        logger.warning("No feature_details validation rules defined for type '%s'", feature_type)
        return

    missing = required - set(feature_details.keys())
    if missing:
        raise ValueError(f"feature_details is missing required field(s) for type '{feature_type}': {sorted(missing)}")


# ---------------------------------------------------------------------------
# MongoDB helpers
# ---------------------------------------------------------------------------


def _get_client(mongo_url: str, credentials: Optional[dict] = None):
    """Return a pymongo MongoClient for *mongo_url*."""
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


def create_indexes(mongo_url: str, credentials: Optional[dict] = None) -> None:
    """Create all required indexes on both collections (idempotent)."""
    try:
        from pymongo import ASCENDING  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pymongo is required. Install it with: pip install pymongo") from exc

    client = _get_client(mongo_url, credentials)
    try:
        db = client[DATABASE]

        # ── instance_level_config ────────────────────────────────────────────
        inst = db[COLLECTION_INSTANCE]

        inst.create_index(
            [
                ("tenant_id", ASCENDING),
                ("subscription_id", ASCENDING),
                ("account", ASCENDING),
                ("region", ASCENDING),
                ("cluster", ASCENDING),
                ("instance", ASCENDING),
            ],
            unique=True,
            name="ux_instance_level_config_tenant_sub_account_region_cluster_instance",
        )
        logger.info("Index 'ux_instance_level_config_tenant_sub_account_region_cluster_instance' ensured on %s.%s", DATABASE, COLLECTION_INSTANCE)

        inst.create_index(
            [
                ("tenant_id", ASCENDING),
                ("subscription_id", ASCENDING),
                ("account", ASCENDING),
                ("region", ASCENDING),
                ("cluster", ASCENDING),
            ],
            name="ix_instance_level_config_tenant_sub_account_region_cluster",
        )
        logger.info("Index 'ix_instance_level_config_tenant_sub_account_region_cluster' ensured on %s.%s", DATABASE, COLLECTION_INSTANCE)

        inst.create_index(
            [("instance_level_features.status", ASCENDING)],
            name="ix_instance_level_config_feature_status",
        )
        logger.info("Index 'ix_instance_level_config_feature_status' ensured on %s.%s", DATABASE, COLLECTION_INSTANCE)

        inst.create_index(
            [("instance_level_features.status_details.error_code", ASCENDING)],
            sparse=True,
            name="ix_instance_level_config_error_code",
        )
        logger.info("Index 'ix_instance_level_config_error_code' ensured on %s.%s", DATABASE, COLLECTION_INSTANCE)

        # ── cluster_level_config ─────────────────────────────────────────────
        clst = db[COLLECTION_CLUSTER]

        clst.create_index(
            [
                ("tenant_id", ASCENDING),
                ("account", ASCENDING),
                ("region", ASCENDING),
                ("cluster", ASCENDING),
            ],
            unique=True,
            name="ux_cluster_level_config_tenant_account_region_cluster",
        )
        logger.info("Index 'ux_cluster_level_config_tenant_account_region_cluster' ensured on %s.%s", DATABASE, COLLECTION_CLUSTER)

        clst.create_index(
            [("tenant_id", ASCENDING), ("account", ASCENDING)],
            name="ix_cluster_level_config_tenant_account",
        )
        logger.info("Index 'ix_cluster_level_config_tenant_account' ensured on %s.%s", DATABASE, COLLECTION_CLUSTER)

    finally:
        client.close()


# ---------------------------------------------------------------------------
# Write helpers — shared feature-entry builder
# ---------------------------------------------------------------------------


def _build_feature_entry(
    feature_type: str,
    feature_details: dict,
    status: str,
    status_details: dict,
    deployment_start: Optional[datetime],
    deployment_end: Optional[datetime],
    now: datetime,
    created_at: Optional[datetime],
    updated_at: Optional[datetime],
) -> dict:
    """Build a single feature entry dict for embedding in the features array."""
    return {
        "type": feature_type,
        "feature_details": feature_details,
        "status": status,
        "status_details": status_details,
        "deployment_start": (deployment_start or now).isoformat(),
        "deployment_end": deployment_end.isoformat() if deployment_end else None,
        "source": FEATURE_SOURCE,
        "created_at": created_at or now,
        "updated_at": updated_at or now,
    }


# ---------------------------------------------------------------------------
# instance_level_config — upsert
# ---------------------------------------------------------------------------


def upsert_instance_feature(
    mongo_url: str,
    *,
    tenant_id: str,
    subscription_id: str,
    region: str,
    account: str,
    cluster: str,
    instance: str,
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
    """Upsert a feature entry inside instance_level_config.

    The parent document is identified by
    (tenant_id, subscription_id, account, region, cluster, instance).
    If the parent does not exist it is created with an empty features array
    and then the entry is pushed.  If a feature entry with the same *type*
    already exists it is updated in-place via arrayFilters; otherwise the
    entry is appended.

    Returns the parent document _id as a string.
    """
    try:
        from pymongo import ReturnDocument  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pymongo is required. Install it with: pip install pymongo") from exc

    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of {sorted(VALID_STATUSES)}")
    validate_feature_details(feature_type, feature_details)

    now = datetime.now(timezone.utc)
    entry = _build_feature_entry(feature_type, feature_details, status, status_details, deployment_start, deployment_end, now, created_at, updated_at)

    parent_filter = {
        "tenant_id": tenant_id,
        "subscription_id": subscription_id,
        "account": account,
        "region": region,
        "cluster": cluster,
        "instance": instance,
    }

    client = _get_client(mongo_url, credentials)
    try:
        collection = client[DATABASE][COLLECTION_INSTANCE]

        # Step 1 — ensure the parent document exists.
        collection.update_one(
            parent_filter,
            {
                "$setOnInsert": {
                    **parent_filter,
                    "instance_level_features": [],
                    "created_at": created_at or now,
                },
                "$set": {"updated_at": updated_at or now},
            },
            upsert=True,
        )

        # Step 2 — check whether a feature entry for this type already exists.
        existing = collection.find_one({**parent_filter, "instance_level_features.type": feature_type})

        if existing:
            # Update the matching array element in-place.
            result = collection.find_one_and_update(
                parent_filter,
                {
                    "$set": {
                        "updated_at": updated_at or now,
                        **{f"instance_level_features.$[elem].{k}": v for k, v in entry.items() if k != "created_at"},
                    }
                },
                array_filters=[{"elem.type": feature_type}],
                return_document=ReturnDocument.AFTER,
            )
        else:
            # Append a brand-new feature entry.
            result = collection.find_one_and_update(
                parent_filter,
                {
                    "$push": {"instance_level_features": entry},
                    "$set": {"updated_at": updated_at or now},
                },
                return_document=ReturnDocument.AFTER,
            )

        doc_id = str(result["_id"])
        logger.info(
            "Instance feature upserted [%s / %s / %s / %s] status=%s id=%s",
            account,
            instance,
            feature_type,
            status,
            status,
            doc_id,
        )
        return doc_id
    finally:
        client.close()


# ---------------------------------------------------------------------------
# cluster_level_config — upsert
# ---------------------------------------------------------------------------


def upsert_cluster_feature(
    mongo_url: str,
    *,
    tenant_id: str,
    region: str,
    account: str,
    cluster: str,
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
    """Upsert a feature entry inside cluster_level_config.

    The parent document is identified by (tenant_id, account, region, cluster).
    Same two-step upsert pattern as upsert_instance_feature.

    Returns the parent document _id as a string.
    """
    try:
        from pymongo import ReturnDocument  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pymongo is required. Install it with: pip install pymongo") from exc

    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of {sorted(VALID_STATUSES)}")
    validate_feature_details(feature_type, feature_details)

    now = datetime.now(timezone.utc)
    entry = _build_feature_entry(feature_type, feature_details, status, status_details, deployment_start, deployment_end, now, created_at, updated_at)

    parent_filter = {
        "tenant_id": tenant_id,
        "account": account,
        "region": region,
        "cluster": cluster,
    }

    client = _get_client(mongo_url, credentials)
    try:
        collection = client[DATABASE][COLLECTION_CLUSTER]

        # Step 1 — ensure the parent document exists.
        collection.update_one(
            parent_filter,
            {
                "$setOnInsert": {
                    **parent_filter,
                    "cluster_level_features": [],
                    "created_at": created_at or now,
                },
                "$set": {"updated_at": updated_at or now},
            },
            upsert=True,
        )

        # Step 2 — check whether a feature entry for this type already exists.
        existing = collection.find_one({**parent_filter, "cluster_level_features.type": feature_type})

        if existing:
            result = collection.find_one_and_update(
                parent_filter,
                {
                    "$set": {
                        "updated_at": updated_at or now,
                        **{f"cluster_level_features.$[elem].{k}": v for k, v in entry.items() if k != "created_at"},
                    }
                },
                array_filters=[{"elem.type": feature_type}],
                return_document=ReturnDocument.AFTER,
            )
        else:
            result = collection.find_one_and_update(
                parent_filter,
                {
                    "$push": {"cluster_level_features": entry},
                    "$set": {"updated_at": updated_at or now},
                },
                return_document=ReturnDocument.AFTER,
            )

        doc_id = str(result["_id"])
        logger.info(
            "Cluster feature upserted [%s / %s / %s] status=%s id=%s",
            account,
            cluster,
            feature_type,
            status,
            doc_id,
        )
        return doc_id
    finally:
        client.close()


# ---------------------------------------------------------------------------
# get helpers
# ---------------------------------------------------------------------------


def get_feature_status_by_id(mongo_url: str, doc_id: str, credentials: Optional[dict] = None) -> Optional[dict]:
    """Fetch a parent document by its ObjectId from either collection.

    Tries instance_level_config first, then cluster_level_config.

    Returns:
        dict with ``_id`` serialised to a string, or None if not found in either collection.

    Raises:
        ValueError: if *doc_id* is not a valid 24-character hex ObjectId.
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
        for col_name in (COLLECTION_INSTANCE, COLLECTION_CLUSTER):
            doc = client[DATABASE][col_name].find_one({"_id": oid})
            if doc is not None:
                doc["_id"] = str(doc["_id"])
                return doc
        return None
    finally:
        client.close()


def get_instance_feature_by_criteria(
    mongo_url: str,
    *,
    tenant_id: str,
    region: str,
    instance_id: str,
    account: str,
    cluster: str,
    subscription_id: str,
    feature_type: str,
    credentials: Optional[dict] = None,
) -> Optional[dict]:
    """Fetch the feature entry for *feature_type* from instance_level_config.

    Returns the matching feature entry dict (not the full parent document),
    or None if the parent or the feature entry does not exist.
    """
    client = _get_client(mongo_url, credentials)
    try:
        filter_doc = {
            "tenant_id": tenant_id,
            "subscription_id": subscription_id,
            "account": account,
            "region": region,
            "cluster": cluster,
            "instance": instance_id,
        }
        doc = client[DATABASE][COLLECTION_INSTANCE].find_one(filter_doc)
        if doc is None:
            return None
        for entry in doc.get("instance_level_features", []):
            if entry.get("type") == feature_type:
                return entry
        return None
    finally:
        client.close()


def get_cluster_feature_by_criteria(
    mongo_url: str,
    *,
    tenant_id: str,
    region: str,
    account: str,
    cluster: str,
    feature_type: str,
    credentials: Optional[dict] = None,
) -> Optional[dict]:
    """Fetch the feature entry for *feature_type* from cluster_level_config.

    Returns the matching feature entry dict (not the full parent document),
    or None if the parent or the feature entry does not exist.
    """
    client = _get_client(mongo_url, credentials)
    try:
        filter_doc = {
            "tenant_id": tenant_id,
            "account": account,
            "region": region,
            "cluster": cluster,
        }
        doc = client[DATABASE][COLLECTION_CLUSTER].find_one(filter_doc)
        if doc is None:
            return None
        for entry in doc.get("cluster_level_features", []):
            if entry.get("type") == feature_type:
                return entry
        return None
    finally:
        client.close()


# ---------------------------------------------------------------------------
# URL redaction helper (keeps passwords out of logs)
# ---------------------------------------------------------------------------


def _redact_url(url: str) -> str:
    """Replace the password component of a MongoDB connection URI with *****."""
    import re

    return re.sub(r"(mongodb(?:\+srv)?://[^:]+:)[^@]+(@)", r"\1*****\2", url)
