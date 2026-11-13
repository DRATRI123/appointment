from fastapi import APIRouter

from app.api.v1 import appointments, auth, catalog, health, meta, organizations, platform, public, scheduling, uploads, users

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
api_router.include_router(uploads.router)
api_router.include_router(public.router)
api_router.include_router(platform.router)
