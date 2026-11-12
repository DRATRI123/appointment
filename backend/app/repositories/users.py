from __future__ import annotations

from sqlalchemy import select

from app.models import User, UserSession
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))

    def get_by_mobile(self, mobile: str) -> User | None:
        return self.db.scalar(select(User).where(User.mobile == mobile, User.deleted_at.is_(None)))

    def get_by_google_sub(self, sub: str) -> User | None:
        return self.db.scalar(select(User).where(User.google_sub == sub, User.deleted_at.is_(None)))


class SessionRepository(BaseRepository[UserSession]):
    model = UserSession

    def get_by_token_hash(self, token_hash: str) -> UserSession | None:
        return self.db.scalar(select(UserSession).where(UserSession.refresh_token_hash == token_hash))

    def list_active_for_user(self, user_id: int) -> list[UserSession]:
        stmt = (
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .order_by(UserSession.last_seen_at.desc().nullslast(), UserSession.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def list_family(self, family_id: str) -> list[UserSession]:
        return list(self.db.scalars(select(UserSession).where(UserSession.family_id == family_id)).all())
