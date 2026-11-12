"""Thin repository base: query helpers shared by concrete repositories."""
from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: Session):
        self.db = db

    def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        self.db.flush()
        return obj

    def get(self, id_: int) -> ModelT | None:
        return self.db.get(self.model, id_)

    def get_by_public_id(self, public_id: str) -> ModelT | None:
        return self.db.scalar(select(self.model).where(self.model.public_id == public_id))  # type: ignore[attr-defined]

    def get_by_public_id_or_404(self, public_id: str, label: str = "Resource") -> ModelT:
        obj = self.get_by_public_id(public_id)
        if obj is None:
            raise NotFoundError(f"{label} not found.")
        return obj
