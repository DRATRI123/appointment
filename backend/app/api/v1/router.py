from fastapi import APIRouter

from app.api.v1 import (
    appointments,
    auth,
    booking_forms,
    catalog,
    customers,
    health,
    meta,
    organizations,
    payments,
    platform,
    public,
    reconciliation,
    refunds,
    scheduling,
    uploads,
    users,
)

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
api_router.include_router(booking_forms.router)
api_router.include_router(payments.upi_router)
api_router.include_router(payments.payments_router)
api_router.include_router(payments.admin_router)
api_router.include_router(payments.coupons_router)
api_router.include_router(refunds.router)
api_router.include_router(reconciliation.router)
api_router.include_router(uploads.router)
api_router.include_router(public.router)
api_router.include_router(platform.router)
