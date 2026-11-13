"""Import every model so SQLAlchemy metadata (and Alembic autogenerate) sees all tables."""
from app.models.admin import AuditLog, SystemSetting
from app.models.appointment import (
    Appointment,
    AppointmentCancellation,
    AppointmentReschedule,
    AppointmentStatusHistory,
    BookingHold,
    Waitlist,
)
from app.models.auth import (
    OrganizationMembership,
    OTPVerification,
    Permission,
    Role,
    RolePermission,
    User,
    UserSession,
)
from app.models.base import Base
from app.models.booking_form import BookingForm, BookingFormField, BookingFormResponse
from app.models.branch import Branch, BranchSetting
from app.models.coupon import Coupon
from app.models.customer import Customer, CustomerDependent, CustomerDocument, CustomerNote
from app.models.integration import (
    APIKey,
    AppointmentExternalEvent,
    ExternalBusyBlock,
    Integration,
    IntegrationLog,
    WebhookEndpoint,
    WebhookEvent,
)
from app.models.notification import Notification, NotificationLog, NotificationTemplate
from app.models.organization import (
    Organization,
    OrganizationDomain,
    OrganizationSetting,
    OrganizationSubscription,
)
from app.models.payment import (
    BankStatementImport,
    BankTransaction,
    Payment,
    PaymentRefund,
    PaymentSubmission,
    PaymentVerificationLog,
    UPIAccount,
)
from app.models.professional import Professional, ProfessionalBranch, ProfessionalService
from app.models.scheduling import (
    AppointmentSlot,
    Holiday,
    ProfessionalLeave,
    Schedule,
    ScheduleException,
)
from app.models.service import Service, ServiceCategory, ServicePackage, ServicePackageItem, ServicePricing

__all__ = [
    "Base",
    "Organization", "OrganizationSetting", "OrganizationDomain", "OrganizationSubscription",
    "Branch", "BranchSetting",
    "User", "UserSession", "OTPVerification", "Role", "Permission", "RolePermission", "OrganizationMembership",
    "Professional", "ProfessionalBranch", "ProfessionalService",
    "ServiceCategory", "Service", "ServicePricing", "ServicePackage", "ServicePackageItem",
    "Schedule", "ScheduleException", "Holiday", "ProfessionalLeave", "AppointmentSlot",
    "Customer", "CustomerDependent", "CustomerNote", "CustomerDocument",
    "Appointment", "AppointmentStatusHistory", "AppointmentReschedule", "AppointmentCancellation",
    "BookingHold", "Waitlist",
    "BookingForm", "BookingFormField", "BookingFormResponse",
    "UPIAccount", "Payment", "PaymentSubmission", "PaymentVerificationLog", "PaymentRefund",
    "BankStatementImport", "BankTransaction",
    "NotificationTemplate", "Notification", "NotificationLog",
    "Integration", "APIKey", "WebhookEndpoint", "WebhookEvent", "IntegrationLog", "AppointmentExternalEvent", "ExternalBusyBlock",
    "AuditLog", "SystemSetting",
    "Coupon",
]
