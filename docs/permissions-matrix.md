# Permissions matrix

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


## Roles

| Role | Code | Typical person |
|---|---|---|
| Platform Super Admin | `platform_super_admin` | Runs the platform (all clinics). Not a clinic role. |
| Organization Owner | `org_owner` | Clinic owner: everything in the clinic, including billing. |
| Organization Admin | `org_admin` | Clinic administrator: everything except billing. |
| Branch Manager | `branch_manager` | Branch admin: runs one branch (when assigned to it). |
| Doctor | `doctor` | Doctor: own schedule and appointments, clinical notes. |
| Professional | `professional` | Therapist / other professional: own appointments. |
| Receptionist | `receptionist` | Front desk: bookings, check-in, patients, cash/UPI records. |
| Accountant | `accountant` | Payments, verification, refunds, reconciliation, reports. |
| Staff | `staff` | Read-only helper. |
| Customer / Patient | `customer` | Patient: own bookings, profile and payments. |

## Permissions by role

✓ = allowed. Columns: `platform_super_admin`, `org_owner`, `org_admin`, `branch_manager`, `doctor`, `professional`, `receptionist`, `accountant`, `staff`, `customer`.

| Permission | What it allows | platform super admin | org owner | org admin | branch manager | doctor | professional | receptionist | accountant | staff | customer |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `platform:manage` | Manage platform configuration, organizations and subscriptions | ✓ |  |  |  |  |  |  |  |  |  |
| `platform:impersonate` | Act inside any organization (audited) | ✓ |  |  |  |  |  |  |  |  |  |
| `organization:read` | View organization profile and settings | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `organization:write` | Edit organization profile, branding and settings | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| `organization:billing` | View and manage subscription | ✓ | ✓ |  |  |  |  |  |  |  |  |
| `branches:read` | View branches | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `branches:write` | Create and edit branches | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `staff:read` | View staff and roles | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `staff:write` | Invite staff, assign roles | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| `roles:write` | Create and edit custom roles | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| `professionals:read` | View professionals | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |
| `professionals:write` | Create and edit professionals | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `professionals:schedule` | Edit schedules, leaves and exceptions | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `services:read` | View services and categories | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |
| `services:write` | Create and edit services, categories, pricing | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `customers:read` | View customer profiles | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |
| `customers:write` | Create and edit customers | ✓ | ✓ | ✓ | ✓ |  |  | ✓ |  |  |  |
| `customers:clinical_read` | Read clinical notes and documents | ✓ | ✓ | ✓ |  | ✓ |  |  |  |  |  |
| `customers:clinical_write` | Write clinical notes and upload documents | ✓ | ✓ | ✓ |  | ✓ |  |  |  |  |  |
| `customers:export` | Export customer data | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| `customers:reveal` | Show a patient's full mobile number and email (each time is audit-logged) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |
| `customers:erase` | Permanently erase a customer's personal data on request | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| `appointments:read` | View appointments | ✓ | ✓ | ✓ | ✓ |  |  | ✓ | ✓ | ✓ |  |
| `appointments:write` | Create, reschedule and cancel appointments | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |
| `appointments:checkin` | Check-in, start and complete appointments | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |
| `appointments:read_own` | View own appointments (professional/customer) | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |  |  | ✓ |
| `booking_forms:read` | View booking forms | ✓ | ✓ | ✓ | ✓ |  |  | ✓ |  |  |  |
| `booking_forms:write` | Build and publish booking forms | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| `payments:read` | View payments | ✓ | ✓ | ✓ | ✓ |  |  | ✓ | ✓ |  |  |
| `payments:record` | Record cash / manual payments | ✓ | ✓ | ✓ | ✓ |  |  | ✓ | ✓ |  |  |
| `payments:verify` | Approve or reject UPI payment submissions | ✓ | ✓ | ✓ | ✓ |  |  |  | ✓ |  |  |
| `upi_accounts:read` | View UPI accounts | ✓ | ✓ | ✓ | ✓ |  |  | ✓ | ✓ |  |  |
| `upi_accounts:write` | Manage UPI accounts and QR codes | ✓ | ✓ | ✓ |  |  |  |  | ✓ |  |  |
| `refunds:request` | Request refunds | ✓ | ✓ | ✓ | ✓ |  |  | ✓ | ✓ |  |  |
| `refunds:approve` | Approve, reject and process refunds | ✓ | ✓ | ✓ |  |  |  |  | ✓ |  |  |
| `reconciliation:manage` | Import bank statements and match transactions | ✓ | ✓ | ✓ |  |  |  |  | ✓ |  |  |
| `notifications:read` | View notification logs | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `notifications:write` | Edit templates and reminder rules | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| `integrations:read` | View integrations | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| `integrations:write` | Connect and configure integrations | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| `api_keys:manage` | Create and revoke API keys and webhooks | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| `website:write` | Edit the public website draft (content, pages, buttons, images) | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| `website:publish` | Publish the public website or restore an earlier version | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |
| `reports:read` | View dashboards and reports | ✓ | ✓ | ✓ | ✓ | ✓ |  |  | ✓ |  |  |
| `reports:export` | Export reports | ✓ | ✓ | ✓ | ✓ |  |  |  | ✓ |  |  |
| `audit_logs:read` | View audit logs | ✓ | ✓ | ✓ |  |  |  |  | ✓ |  |  |
