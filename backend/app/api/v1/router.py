from fastapi import APIRouter

from app.api.v1 import (
    appointments,
    auth,
    booking_forms,
    catalog,
    customers,
    developers,
    health,
    integrations,
    meta,
    notifications,
    organizations,
    payments,
    platform,
    platform_database,
    platform_integrations,
    public,
    reconciliation,
    refunds,
    reports,
    scheduling,
    uploads,
    users,
    verification,
    website,
)
from app.core.config import get_settings

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(meta.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(organizations.router)
api_router.include_router(catalog.router)
api_router.include_router(scheduling.router)
api_router.include_router(appointments.router)
api_router.include_router(appointments.customer_router)
api_router.include_router(customers.router)
api_router.include_router(customers.self_router)
api_router.include_router(customers.files_router)
api_router.include_router(booking_forms.router)
api_router.include_router(payments.upi_router)
api_router.include_router(payments.payments_router)
api_router.include_router(payments.admin_router)
api_router.include_router(payments.coupons_router)
api_router.include_router(refunds.router)
api_router.include_router(reconciliation.router)
api_router.include_router(notifications.router)
api_router.include_router(notifications.me_router)
api_router.include_router(integrations.router)
api_router.include_router(integrations.appointments_router)
api_router.include_router(integrations.feeds_router)
api_router.include_router(reports.router)
api_router.include_router(developers.router)
api_router.include_router(uploads.router)
api_router.include_router(website.router)
api_router.include_router(verification.router)

if get_settings().app_env in ("development", "test"):
    from app.api.v1 import dev

    api_router.include_router(dev.router)
api_router.include_router(public.router)
api_router.include_router(platform_database.router)
api_router.include_router(platform_integrations.router)  # before /platform/{...} routes
api_router.include_router(platform.router)
