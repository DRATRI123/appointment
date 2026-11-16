"""Google Analytics 4 and Google Tag Manager on the clinic's public booking pages.

The IDs are public by design (they appear in every website that uses them). Nothing loads until the visitor agrees
(consent banner, Google Consent Mode v2 defaults to "denied"). Events: page_view, booking_start, booking_complete and
booking_abandoned, with the clinic slug and the booking source only; never names, numbers or what the visit is for.
A GA4 property cannot be checked from the server without extra keys, so the hub shows these IDs as "Active", not
"Connected".
"""
from __future__ import annotations

import re

from app.connectors.base import Adapter
from app.integrations.http import IntegrationAPIError

GA4_ID = re.compile(r"^G-[A-Z0-9]{4,12}$")
GTM_ID = re.compile(r"^GTM-[A-Z0-9]{4,10}$")


def validate(measurement_id: str | None, gtm_id: str | None) -> None:
    if not measurement_id and not gtm_id:
        raise IntegrationAPIError("Enter a GA4 measurement ID or a Tag Manager container ID.")
    if measurement_id and not GA4_ID.match(measurement_id):
        raise IntegrationAPIError("A GA4 measurement ID looks like G-ABC123XYZ (GA4 → Admin → Data streams).")
    if gtm_id and not GTM_ID.match(gtm_id):
        raise IntegrationAPIError("A Tag Manager container ID looks like GTM-ABC1234.")


class Analytics(Adapter):
    def test(self) -> str:
        cfg = self.ctx.config
        validate(cfg.get("measurement_id"), cfg.get("gtm_container_id"))
        return "IDs are valid. Open your booking page, accept analytics, and check GA4 → Reports → Realtime."


def public_settings(db, org) -> dict | None:
    """What the public booking page needs (only when the clinic switched it on)."""
    from sqlalchemy import select

    from app.models import Integration

    integ = db.scalar(select(Integration).where(Integration.organization_id == org.id, Integration.provider == "ga4", Integration.is_enabled.is_(True)))
    if integ is None:
        return None
    cfg = integ.config or {}
    mid, gtm = cfg.get("measurement_id"), cfg.get("gtm_container_id")
    if (mid and not GA4_ID.match(mid)) or (gtm and not GTM_ID.match(gtm)) or not (mid or gtm):
        return None
    return {"ga4_measurement_id": mid or None, "gtm_container_id": gtm or None}
