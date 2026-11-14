"""Permission catalogue and default role → permission matrix.

Permission codes are ``module:action``. The seed script writes these into ``permissions`` and the
system ``roles``; organizations can clone a system role into a custom role and adjust it.
"""
from __future__ import annotations

from app.core.enums import SystemRole

PERMISSIONS: dict[str, str] = {
    # platform
    "platform:manage": "Manage platform configuration, organizations and subscriptions",
    "platform:impersonate": "Act inside any organization (audited)",
    # organization
    "organization:read": "View organization profile and settings",
    "organization:write": "Edit organization profile, branding and settings",
    "organization:billing": "View and manage subscription",
    # branches
    "branches:read": "View branches",
    "branches:write": "Create and edit branches",
    # staff / rbac
    "staff:read": "View staff and roles",
    "staff:write": "Invite staff, assign roles",
    "roles:write": "Create and edit custom roles",
    # professionals
    "professionals:read": "View professionals",
    "professionals:write": "Create and edit professionals",
    "professionals:schedule": "Edit schedules, leaves and exceptions",
    # services
    "services:read": "View services and categories",
    "services:write": "Create and edit services, categories, pricing",
    # customers
    "customers:read": "View customer profiles",
    "customers:write": "Create and edit customers",
    "customers:clinical_read": "Read clinical notes and documents",
    "customers:clinical_write": "Write clinical notes and upload documents",
    "customers:export": "Export customer data",
    "customers:erase": "Permanently erase a customer's personal data on request",
    # appointments
    "appointments:read": "View appointments",
    "appointments:write": "Create, reschedule and cancel appointments",
    "appointments:checkin": "Check-in, start and complete appointments",
    "appointments:read_own": "View own appointments (professional/customer)",
    # booking forms
    "booking_forms:read": "View booking forms",
    "booking_forms:write": "Build and publish booking forms",
    # payments
    "payments:read": "View payments",
    "payments:record": "Record cash / manual payments",
    "payments:verify": "Approve or reject UPI payment submissions",
    "upi_accounts:read": "View UPI accounts",
    "upi_accounts:write": "Manage UPI accounts and QR codes",
    "refunds:request": "Request refunds",
    "refunds:approve": "Approve, reject and process refunds",
    "reconciliation:manage": "Import bank statements and match transactions",
    # notifications
    "notifications:read": "View notification logs",
    "notifications:write": "Edit templates and reminder rules",
    # integrations
    "integrations:read": "View integrations",
    "integrations:write": "Connect and configure integrations",
    "api_keys:manage": "Create and revoke API keys and webhooks",
    # reports
    "reports:read": "View dashboards and reports",
    "reports:export": "Export reports",
    # audit
    "audit_logs:read": "View audit logs",
}

_ALL = tuple(PERMISSIONS)
_READ_ONLY_OPS = (
    "organization:read", "branches:read", "professionals:read", "services:read",
    "customers:read", "appointments:read", "payments:read", "reports:read",
)

ROLE_PERMISSIONS: dict[SystemRole, tuple[str, ...]] = {
    SystemRole.PLATFORM_SUPER_ADMIN: _ALL,
    SystemRole.ORG_OWNER: tuple(p for p in _ALL if not p.startswith("platform:")),
    SystemRole.ORG_ADMIN: tuple(
        p for p in _ALL if not p.startswith("platform:") and p != "organization:billing"
    ),
    SystemRole.BRANCH_MANAGER: _READ_ONLY_OPS + (
        "branches:write", "professionals:write", "professionals:schedule", "services:write",
        "customers:write", "appointments:write", "appointments:checkin", "payments:record",
        "payments:verify", "upi_accounts:read", "refunds:request", "staff:read",
        "booking_forms:read", "notifications:read", "reports:export",
    ),
    SystemRole.DOCTOR: (
        "organization:read", "branches:read", "professionals:read", "services:read",
        "customers:read", "customers:clinical_read", "customers:clinical_write",
        "appointments:read_own", "appointments:checkin", "appointments:write", "reports:read",
    ),
    SystemRole.PROFESSIONAL: (
        "organization:read", "branches:read", "professionals:read", "services:read",
        "customers:read", "appointments:read_own", "appointments:checkin", "appointments:write",
    ),
    SystemRole.RECEPTIONIST: (
        "organization:read", "branches:read", "professionals:read", "services:read",
        "customers:read", "customers:write", "appointments:read", "appointments:write",
        "appointments:checkin", "payments:read", "payments:record", "upi_accounts:read",
        "booking_forms:read", "refunds:request",
    ),
    SystemRole.ACCOUNTANT: (
        "organization:read", "branches:read", "appointments:read", "payments:read",
        "payments:verify", "payments:record", "upi_accounts:read", "upi_accounts:write",
        "refunds:approve", "refunds:request", "reconciliation:manage", "reports:read",
        "reports:export", "audit_logs:read",
    ),
    SystemRole.STAFF: (
        "organization:read", "branches:read", "professionals:read", "services:read",
        "appointments:read",
    ),
    SystemRole.CUSTOMER: ("appointments:read_own",),
}

ROLE_LABELS: dict[SystemRole, str] = {
    SystemRole.PLATFORM_SUPER_ADMIN: "Platform Super Admin",
    SystemRole.ORG_OWNER: "Organization Owner",
    SystemRole.ORG_ADMIN: "Organization Admin",
    SystemRole.BRANCH_MANAGER: "Branch Manager",
    SystemRole.DOCTOR: "Doctor",
    SystemRole.PROFESSIONAL: "Professional",
    SystemRole.RECEPTIONIST: "Receptionist",
    SystemRole.ACCOUNTANT: "Accountant",
    SystemRole.STAFF: "Staff",
    SystemRole.CUSTOMER: "Customer / Patient",
}

for _role, _perms in ROLE_PERMISSIONS.items():
    _unknown = set(_perms) - set(PERMISSIONS)
    if _unknown:  # fail fast at import time; never silently grant an undefined permission
        raise RuntimeError(f"Unknown permissions for {_role}: {_unknown}")
