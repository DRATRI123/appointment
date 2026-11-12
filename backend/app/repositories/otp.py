from __future__ import annotations

from sqlalchemy import select

from app.models import OTPVerification
from app.repositories.base import BaseRepository


class OTPRepository(BaseRepository[OTPVerification]):
    model = OTPVerification

    def latest(self, identifier: str, purpose: str) -> OTPVerification | None:
        stmt = (
            select(OTPVerification)
            .where(OTPVerification.identifier == identifier, OTPVerification.purpose == purpose)
            .order_by(OTPVerification.id.desc())
        )
        return self.db.scalars(stmt).first()

    def latest_unconsumed(self, identifier: str, purpose: str) -> OTPVerification | None:
        stmt = (
            select(OTPVerification)
            .where(
                OTPVerification.identifier == identifier,
                OTPVerification.purpose == purpose,
                OTPVerification.consumed_at.is_(None),
            )
            .order_by(OTPVerification.id.desc())
        )
        return self.db.scalars(stmt).first()

    def get_by_code_hash(self, purpose: str, code_hash: str) -> OTPVerification | None:
        stmt = select(OTPVerification).where(
            OTPVerification.purpose == purpose,
            OTPVerification.code_hash == code_hash,
            OTPVerification.consumed_at.is_(None),
        )
        return self.db.scalars(stmt).first()
