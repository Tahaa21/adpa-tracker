"""Shared enum-like string constants for the internal data model.

Stored as plain strings in the DB (portable across Postgres/SQLite, simple to
migrate) and validated at the Pydantic schema layer.
"""
from enum import Enum


class AssetType(str, Enum):
    USER = "user"
    GROUP = "group"
    COMPUTER = "computer"
    DOMAIN = "domain"
    POLICY = "policy"
    SERVICE_ACCOUNT = "service_account"
    UNKNOWN = "unknown"


class Criticality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Priority(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Category(str, Enum):
    TIER_0 = "TIER_0"
    IDENTITY_EXPOSURE = "IDENTITY_EXPOSURE"
    ACCOUNT_HYGIENE = "ACCOUNT_HYGIENE"
    POLICY_CONFIGURATION = "POLICY_CONFIGURATION"
    PRIVILEGE = "PRIVILEGE"
    CREDENTIAL_EXPOSURE = "CREDENTIAL_EXPOSURE"
    DELEGATION = "DELEGATION"
    TRUST = "TRUST"
    OTHER = "OTHER"


class NormalizedFindingType(str, Enum):
    PASSWORD_NOT_REQUIRED = "PASSWORD_NOT_REQUIRED"
    PASSWORD_NEVER_EXPIRES = "PASSWORD_NEVER_EXPIRES"
    REVERSIBLE_ENCRYPTION = "REVERSIBLE_ENCRYPTION"
    PRIVILEGED_GROUP_MEMBERSHIP = "PRIVILEGED_GROUP_MEMBERSHIP"
    DOMAIN_ADMIN_MEMBERSHIP = "DOMAIN_ADMIN_MEMBERSHIP"
    DCSYNC_EXPOSURE = "DCSYNC_EXPOSURE"
    PASSWORD_REUSE = "PASSWORD_REUSE"
    LEAKED_CREDENTIAL = "LEAKED_CREDENTIAL"
    WEAK_PASSWORD = "WEAK_PASSWORD"
    DORMANT_PRIVILEGED_ACCOUNT = "DORMANT_PRIVILEGED_ACCOUNT"
    DELEGATION_RISK = "DELEGATION_RISK"
    ACL_ABUSE = "ACL_ABUSE"
    PASSWORD_POLICY_WEAKNESS = "PASSWORD_POLICY_WEAKNESS"
    SERVICE_ACCOUNT_RISK = "SERVICE_ACCOUNT_RISK"
    TRUST_RISK = "TRUST_RISK"
    UNKNOWN = "UNKNOWN"


class FindingStatus(str, Enum):
    OPEN = "OPEN"
    TRIAGED = "TRIAGED"
    ASSIGNED = "ASSIGNED"
    IN_REMEDIATION = "IN_REMEDIATION"
    READY_FOR_VALIDATION = "READY_FOR_VALIDATION"
    VALIDATED = "VALIDATED"
    CLOSED = "CLOSED"
    RISK_ACCEPTED = "RISK_ACCEPTED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    DEFERRED = "DEFERRED"
    REOPENED = "REOPENED"


class ValidationResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
