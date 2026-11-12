"""Domain enumerations.

Values are persisted as short strings so new values can be added without a DDL change.
"""
from __future__ import annotations

from enum import StrEnum


class OrganizationStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class MembershipStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class SystemRole(StrEnum):
    PLATFORM_SUPER_ADMIN = "platform_super_admin"
    ORG_OWNER = "org_owner"
    ORG_ADMIN = "org_admin"
    BRANCH_MANAGER = "branch_manager"
    DOCTOR = "doctor"
    PROFESSIONAL = "professional"
    RECEPTIONIST = "receptionist"
    ACCOUNTANT = "accountant"
    STAFF = "staff"
    CUSTOMER = "customer"


class OTPPurpose(StrEnum):
    LOGIN = "login"
    REGISTER = "register"
    VERIFY_MOBILE = "verify_mobile"
    VERIFY_EMAIL = "verify_email"
    PASSWORD_RESET = "password_reset"
    BOOKING = "booking"


class OTPChannel(StrEnum):
    SMS = "sms"
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class ConsultationMode(StrEnum):
    IN_PERSON = "in_person"
    ONLINE = "online"
    BOTH = "both"


class ServicePaymentMode(StrEnum):
    FREE = "free"
    FULL_ADVANCE = "full_advance"
    PARTIAL_ADVANCE = "partial_advance"
    PAY_AT_CLINIC = "pay_at_clinic"
    OPTIONAL_ADVANCE = "optional_advance"


class ServiceKind(StrEnum):
    STANDARD = "standard"
    ADDON = "addon"
    FOLLOW_UP = "follow_up"
    PACKAGE = "package"


class AppointmentStatus(StrEnum):
    DRAFT = "draft"
    PENDING_PAYMENT = "pending_payment"
    PENDING_VERIFICATION = "pending_verification"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"
    NO_SHOW = "no_show"
    EXPIRED = "expired"


# Statuses that occupy a slot. Used by the partial unique index and availability engine.
ACTIVE_APPOINTMENT_STATUSES: tuple[str, ...] = (
    AppointmentStatus.PENDING_PAYMENT,
    AppointmentStatus.PENDING_VERIFICATION,
    AppointmentStatus.CONFIRMED,
    AppointmentStatus.CHECKED_IN,
    AppointmentStatus.IN_PROGRESS,
)


class AppointmentSource(StrEnum):
    ONLINE = "online"
    RECEPTION = "reception"
    WALK_IN = "walk_in"
    PROFESSIONAL = "professional"
    API = "api"
    RECURRING = "recurring"


class HoldStatus(StrEnum):
    ACTIVE = "active"
    CONVERTED = "converted"
    RELEASED = "released"
    EXPIRED = "expired"


class LeaveType(StrEnum):
    LEAVE = "leave"
    HOLIDAY = "holiday"
    BLOCKED = "blocked"


class PaymentStatus(StrEnum):
    INITIATED = "initiated"
    AWAITING_PAYMENT = "awaiting_payment"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REFUND_REQUESTED = "refund_requested"
    REFUND_PROCESSED = "refund_processed"


class PaymentMethod(StrEnum):
    UPI_QR = "upi_qr"
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    PAY_AT_CLINIC = "pay_at_clinic"
    FREE = "free"


class PaymentKind(StrEnum):
    ADVANCE = "advance"
    FULL = "full"
    BALANCE = "balance"


class RefundStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSED = "processed"
    CANCELLED = "cancelled"


class BankImportStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSED = "parsed"
    FAILED = "failed"
    RECONCILED = "reconciled"


class BankTransactionMatchStatus(StrEnum):
    UNMATCHED = "unmatched"
    SUGGESTED = "suggested"
    MATCHED = "matched"
    IGNORED = "ignored"


class NotificationChannel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    IN_APP = "in_app"
    PUSH = "push"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    READ = "read"


class NotificationEvent(StrEnum):
    APPOINTMENT_CREATED = "appointment.created"
    PAYMENT_SUBMITTED = "payment.submitted"
    PAYMENT_VERIFIED = "payment.verified"
    PAYMENT_REJECTED = "payment.rejected"
    APPOINTMENT_CONFIRMED = "appointment.confirmed"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
    APPOINTMENT_REMINDER = "appointment.reminder"
    REFUND_REQUESTED = "refund.requested"
    REFUND_PROCESSED = "refund.processed"
    OTP = "auth.otp"


class IntegrationProvider(StrEnum):
    GOOGLE_CALENDAR = "google_calendar"
    GOOGLE_MEET = "google_meet"
    ZOOM = "zoom"
    GMAIL = "gmail"
    SMTP = "smtp"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    SHOPIFY = "shopify"
    CRM = "crm"
    ACCOUNTING = "accounting"
    CUSTOM = "custom"


class IntegrationStatus(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"
    DISABLED = "disabled"


class WebhookDeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD = "dead"


class FormFieldType(StrEnum):
    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    EMAIL = "email"
    MOBILE = "mobile"
    DROPDOWN = "dropdown"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    DATE = "date"
    FILE = "file"
    MULTI_SELECT = "multi_select"


class FormScope(StrEnum):
    ORGANIZATION = "organization"
    BRANCH = "branch"
    SERVICE = "service"


class SubscriptionStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNDISCLOSED = "undisclosed"
