"""Write docs/permissions-matrix.md from the role definitions in code: ``python -m app.ops.permissions_matrix``.

The test suite checks the document matches the code and that every role really gets exactly these permissions.
"""
from __future__ import annotations

from pathlib import Path

from app.security.permissions import PERMISSIONS, ROLE_LABELS, ROLE_PERMISSIONS

DOC = Path(__file__).resolve().parents[3] / "docs" / "permissions-matrix.md"

INTRO = """# Permissions matrix

Generated from `backend/app/security/permissions.py` by `python -m app.ops.permissions_matrix`. Do not edit by hand:
`tests/test_permissions_matrix.py` fails if this file and the code differ, and checks every role against real
endpoints.

## How access is decided (every request, on the server)

1. **Signed in?** Otherwise `401`.
2. **Which clinic?** The member's own clinic only (`X-Organization-Id`). Another clinic's records do not exist for
   them (`404`), and every query is limited to the clinic.
3. **Which branch?** Staff assigned to one branch (branch manager, receptionist, doctor, staff) only see that branch's
   appointments, holds, payments, refunds, schedules and the patients who visit it. Owners and administrators see
   every branch.
4. **Which permission?** The endpoint's required permission must be in the role's list below, otherwise `403`.
5. **Own records only** where it applies: doctors and professionals with `appointments:read_own` see only their own
   appointments; patients see only their own bookings, profile and payments (or a booking by its private link).
6. **Super admin** (platform): separate from clinic roles, created only from the server
   (docs/superadmin-setup.md), must use two-step sign-in, optional IP allow-list; every action inside a clinic is
   audit-logged.
7. **API keys** act as their creator, limited to the key's scopes and the creator's branch; they can never record,
   verify or refund money.

The browser only hides menu items; it is never what protects data.

"""


def render() -> str:
    roles = [r for r in ROLE_PERMISSIONS]
    lines = [INTRO, "## Roles\n", "| Role | Code | Typical person |", "|---|---|---|"]
    who = {
        "platform_super_admin": "Runs the platform (all clinics). Not a clinic role.",
        "org_owner": "Clinic owner: everything in the clinic, including billing.",
        "org_admin": "Clinic administrator: everything except billing.",
        "branch_manager": "Branch admin: runs one branch (when assigned to it).",
        "doctor": "Doctor: own schedule and appointments, clinical notes.",
        "professional": "Therapist / other professional: own appointments.",
        "receptionist": "Front desk: bookings, check-in, patients, cash/UPI records.",
        "accountant": "Payments, verification, refunds, reconciliation, reports.",
        "staff": "Read-only helper.",
        "customer": "Patient: own bookings, profile and payments.",
    }
    for r in roles:
        lines.append(f"| {ROLE_LABELS.get(r, r.value)} | `{r.value}` | {who.get(r.value, '')} |")
    lines += ["", "## Permissions by role\n", "✓ = allowed. Columns: " + ", ".join(f"`{r.value}`" for r in roles) + ".\n"]
    lines.append("| Permission | What it allows | " + " | ".join(r.value.replace("_", " ") for r in roles) + " |")
    lines.append("|---|---|" + "---|" * len(roles))
    for code, label in PERMISSIONS.items():
        marks = " | ".join("✓" if code in ROLE_PERMISSIONS[r] else "" for r in roles)
        lines.append(f"| `{code}` | {label} | {marks} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(render(), encoding="utf-8")
    print(f"Wrote {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
