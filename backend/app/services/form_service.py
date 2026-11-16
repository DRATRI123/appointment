"""No-code booking forms: definitions, versions, templates, resolution and server-side validation."""
from __future__ import annotations

import re
import secrets
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.core.time import utcnow
from app.models import Appointment, BookingForm, BookingFormField, BookingFormResponse, Branch, Customer, Organization, Service, User
from app.schemas.booking_form import BookingFormCreate, BookingFormRead, BookingFormUpdate, FieldCondition, FormFieldInput, FormFieldRead, FormResponseRead, PublicForm
from app.security.identifiers import normalize_email, normalize_mobile
from app.services.audit_service import RequestMeta, record_audit
from app.services.catalog_service import ids_to_public, slugify

DEFAULT_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Patient intake", "slug": "template-patient-intake", "description": "Basic medical history for a first consultation.",
        "fields": [
            {"key": "reason_for_visit", "label": "Reason for visit", "field_type": "textarea", "is_required": True, "sort_order": 1},
            {"key": "existing_conditions", "label": "Existing conditions", "field_type": "multi_select", "sort_order": 2, "options": [{"value": "diabetes", "label": "Diabetes"}, {"value": "hypertension", "label": "Hypertension"}, {"value": "thyroid", "label": "Thyroid"}, {"value": "none", "label": "None"}]},
            {"key": "allergies", "label": "Known allergies", "field_type": "text", "sort_order": 3},
            {"key": "on_medication", "label": "Currently taking medication?", "field_type": "radio", "is_required": True, "sort_order": 4, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
            {"key": "medication_details", "label": "Which medication?", "field_type": "textarea", "sort_order": 5, "conditions": [{"field": "on_medication", "operator": "equals", "value": "yes"}]},
            {"key": "reports", "label": "Previous reports (optional)", "field_type": "file", "sort_order": 6, "validation": {"max_files": 3}},
        ],
    },
    {
        "name": "Skin consultation", "slug": "template-skin-consultation", "description": "Dermatology pre-visit questions.",
        "fields": [
            {"key": "concern", "label": "Main skin concern", "field_type": "dropdown", "is_required": True, "sort_order": 1, "options": [{"value": "acne", "label": "Acne"}, {"value": "pigmentation", "label": "Pigmentation"}, {"value": "hair", "label": "Hair loss"}, {"value": "other", "label": "Other"}]},
            {"key": "concern_other", "label": "Please describe", "field_type": "text", "sort_order": 2, "conditions": [{"field": "concern", "operator": "equals", "value": "other"}]},
            {"key": "duration_months", "label": "Since how many months?", "field_type": "number", "sort_order": 3, "validation": {"min": 0, "max": 600}},
            {"key": "photo", "label": "Photo of the affected area", "field_type": "file", "sort_order": 4, "validation": {"max_files": 2, "accept": ["image/jpeg", "image/png", "image/webp"]}},
        ],
    },
    {
        "name": "Consent & contact", "slug": "template-consent", "description": "Consent acknowledgement and emergency contact.",
        "fields": [
            {"key": "emergency_contact", "label": "Emergency contact number", "field_type": "mobile", "is_required": True, "sort_order": 1},
            {"key": "consent_treatment", "label": "I consent to consultation and treatment", "field_type": "checkbox", "is_required": True, "sort_order": 2},
            {"key": "consent_whatsapp", "label": "Send me reminders on WhatsApp", "field_type": "checkbox", "sort_order": 3},
        ],
    },
]


HIDDEN_ANSWER = "Hidden: clinical access needed"


def seal_answers(form: BookingForm, answers: dict[str, Any]) -> dict[str, Any]:
    """Answers to fields marked sensitive (medical history, medicines, ...) are encrypted at rest (AES-256-GCM)."""
    import json

    from app.security.crypto import encrypt_text

    sensitive = {f.key for f in form.fields if f.is_sensitive}
    return {k: ({"enc": encrypt_text(json.dumps(v))} if k in sensitive and v not in (None, "", []) else v) for k, v in answers.items()}


def open_answers(answers: dict[str, Any] | None, show_sensitive: bool) -> dict[str, Any] | None:
    """Decrypt sensitive answers for people allowed to see them; everyone else gets a placeholder, never the value."""
    import json

    from app.security.crypto import decrypt_text

    if answers is None:
        return None
    out: dict[str, Any] = {}
    for k, v in answers.items():
        if isinstance(v, dict) and set(v) == {"enc"}:
            out[k] = json.loads(decrypt_text(v["enc"])) if show_sensitive else HIDDEN_ANSWER
        else:
            out[k] = v
    return out


class FormService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()

    # ------------------------------------------------------------ lookups
    def get(self, public_id: str) -> BookingForm:
        form = self.db.scalar(select(BookingForm).options(selectinload(BookingForm.fields)).where(BookingForm.public_id == public_id, BookingForm.organization_id == self.org.id, BookingForm.deleted_at.is_(None)))
        if form is None:
            raise NotFoundError("Booking form not found.")
        return form

    def list(self, *, include_templates: bool = True, latest_only: bool = True) -> list[BookingForm]:
        stmt = select(BookingForm).options(selectinload(BookingForm.fields)).where(BookingForm.organization_id == self.org.id, BookingForm.deleted_at.is_(None))
        if not include_templates:
            stmt = stmt.where(BookingForm.is_template.is_(False))
        rows = list(self.db.scalars(stmt.order_by(BookingForm.is_template, BookingForm.name, BookingForm.version.desc())).all())
        if latest_only:
            seen: set[str] = set()
            latest = []
            for f in rows:
                if f.slug in seen:
                    continue
                seen.add(f.slug)
                latest.append(f)
            rows = latest
        return rows

    def templates(self) -> list[dict[str, Any]]:
        return DEFAULT_TEMPLATES

    # ------------------------------------------------------------- create
    def create(self, payload: BookingFormCreate) -> BookingForm:
        fields = list(payload.fields)
        if payload.clone_from:
            fields = self._fields_from_source(payload.clone_from) + fields
        slug = payload.slug or self._unique_slug(payload.name)
        if payload.slug and self.db.scalar(select(BookingForm.id).where(BookingForm.organization_id == self.org.id, BookingForm.slug == payload.slug, BookingForm.deleted_at.is_(None))):
            raise ConflictError("This slug is already in use.", code="slug_taken")
        form = BookingForm(
            organization_id=self.org.id, name=payload.name, slug=slug, version=1, scope=payload.scope,
            branch_id=self._branch_id(payload.branch_id) if payload.scope == "branch" else None,
            description=payload.description, instructions=payload.instructions, is_template=payload.is_template, is_published=False, is_active=True, settings=payload.settings,
        )
        self.db.add(form)
        self.db.flush()
        self._replace_fields(form, fields)
        record_audit(self.db, action="booking_form.created", actor=self.actor, organization_id=self.org.id, entity_type="booking_form", entity_id=form.public_id, after={"name": form.name}, meta=self.meta)
        return self.get(form.public_id)

    def _fields_from_source(self, source: str) -> list[FormFieldInput]:
        template = next((t for t in DEFAULT_TEMPLATES if t["slug"] == source), None)
        if template:
            return [FormFieldInput(**f) for f in template["fields"]]
        src = self.get(source)
        return [self._field_input(f) for f in src.fields]

    @staticmethod
    def _field_input(f: BookingFormField) -> FormFieldInput:
        return FormFieldInput(key=f.key, label=f.label, field_type=f.field_type, placeholder=f.placeholder, help_text=f.help_text, is_required=f.is_required, sort_order=f.sort_order,
                              options=f.options, validation=f.validation, conditions=f.conditions, default_value=(f.default_value or {}).get("v") if isinstance(f.default_value, dict) else f.default_value, is_sensitive=f.is_sensitive)

    def _unique_slug(self, name: str) -> str:
        base = slugify(name)
        slug = base
        while self.db.scalar(select(BookingForm.id).where(BookingForm.organization_id == self.org.id, BookingForm.slug == slug, BookingForm.deleted_at.is_(None))):
            slug = f"{base}-{secrets.token_hex(2)}"
        return slug

    def _branch_id(self, public_id: str | None) -> int | None:
        if not public_id:
            raise ValidationFailed("branch_id is required for branch-scoped forms.")
        b = self.db.scalar(select(Branch).where(Branch.public_id == public_id, Branch.organization_id == self.org.id, Branch.deleted_at.is_(None)))
        if b is None:
            raise NotFoundError("Branch not found.")
        return b.id

    def _replace_fields(self, form: BookingForm, fields: list[FormFieldInput]) -> None:
        for existing in list(form.fields):
            self.db.delete(existing)
        self.db.flush()
        keys = {f.key for f in fields}
        for f in fields:
            for cond in f.conditions or []:
                if cond.field not in keys or cond.field == f.key:
                    raise ValidationFailed(f"Field '{f.key}' has a condition on unknown field '{cond.field}'.", code="bad_condition")
            self.db.add(BookingFormField(
                form_id=form.id, key=f.key, label=f.label, field_type=f.field_type, placeholder=f.placeholder, help_text=f.help_text, is_required=f.is_required,
                sort_order=f.sort_order, options=[o.model_dump() for o in f.options] if f.options else None, validation=f.validation.model_dump(exclude_none=True) if f.validation else None,
                conditions=[c.model_dump() for c in f.conditions] if f.conditions else None, default_value={"v": f.default_value} if f.default_value is not None else None, is_sensitive=f.is_sensitive,
            ))
        self.db.flush()
        self.db.expire(form, ["fields"])

    # ------------------------------------------------------------- update
    def update(self, form: BookingForm, payload: BookingFormUpdate) -> BookingForm:
        data = payload.model_dump(exclude_unset=True, exclude={"fields", "branch_id"})
        if form.is_published and payload.fields is not None:
            # Published forms are immutable: editing fields creates a new draft version.
            form = self._new_version(form)
        for k, v in data.items():
            setattr(form, k, v)
        if "branch_id" in payload.model_fields_set or data.get("scope") == "branch":
            form.branch_id = self._branch_id(payload.branch_id) if (payload.scope or form.scope) == "branch" else None
        if payload.fields is not None:
            self._replace_fields(form, payload.fields)
        self.db.flush()
        record_audit(self.db, action="booking_form.updated", actor=self.actor, organization_id=self.org.id, entity_type="booking_form", entity_id=form.public_id, after={"version": form.version}, meta=self.meta)
        return self.get(form.public_id)

    def _new_version(self, form: BookingForm) -> BookingForm:
        max_version = self.db.scalar(select(func.max(BookingForm.version)).where(BookingForm.organization_id == self.org.id, BookingForm.slug == form.slug)) or form.version
        draft = BookingForm(
            organization_id=self.org.id, name=form.name, slug=form.slug, version=max_version + 1, scope=form.scope, branch_id=form.branch_id, description=form.description,
            instructions=form.instructions, is_template=form.is_template, is_published=False, is_active=True, settings=form.settings,
        )
        self.db.add(draft)
        self.db.flush()
        self._replace_fields(draft, [self._field_input(f) for f in form.fields])
        return self.get(draft.public_id)

    def publish(self, form: BookingForm) -> BookingForm:
        if form.is_template:
            raise ValidationFailed("Templates are not published; create a form from the template.", code="is_template")
        if not form.fields:
            raise ValidationFailed("Add at least one field before publishing.", code="no_fields")
        previous = self.db.scalars(select(BookingForm).where(BookingForm.organization_id == self.org.id, BookingForm.slug == form.slug, BookingForm.id != form.id, BookingForm.is_published.is_(True))).all()
        for p in previous:
            p.is_published = False
            # services pointing at the previous version follow the new one
            for svc in self.db.scalars(select(Service).where(Service.booking_form_id == p.id)).all():
                svc.booking_form_id = form.id
        form.is_published = True
        form.is_active = True
        self.db.flush()
        record_audit(self.db, action="booking_form.published", actor=self.actor, organization_id=self.org.id, entity_type="booking_form", entity_id=form.public_id, after={"version": form.version}, meta=self.meta)
        return form

    def delete(self, form: BookingForm) -> None:
        in_use = self.db.scalar(select(func.count()).select_from(Service).where(Service.booking_form_id == form.id, Service.deleted_at.is_(None))) or 0
        if in_use:
            raise ConflictError("Detach this form from its services first.", code="form_in_use")
        form.deleted_at = utcnow()
        form.is_published = False
        form.is_active = False
        self.db.flush()
        record_audit(self.db, action="booking_form.deleted", actor=self.actor, organization_id=self.org.id, entity_type="booking_form", entity_id=form.public_id, meta=self.meta)

    def assign_to_service(self, form: BookingForm | None, service_public_id: str) -> Service:
        svc = self.db.scalar(select(Service).where(Service.public_id == service_public_id, Service.organization_id == self.org.id, Service.deleted_at.is_(None)))
        if svc is None:
            raise NotFoundError("Service not found.")
        svc.booking_form_id = form.id if form else None
        self.db.flush()
        record_audit(self.db, action="booking_form.assigned", actor=self.actor, organization_id=self.org.id, entity_type="service", entity_id=svc.public_id, after={"form": form.public_id if form else None}, meta=self.meta)
        return svc

    # --------------------------------------------------------- resolution
    def resolve(self, service: Service | None, branch: Branch | None) -> BookingForm | None:
        """Service-assigned form → branch form → organization default (published and active only)."""
        if service and service.booking_form_id:
            form = self.db.get(BookingForm, service.booking_form_id)
            if form and form.is_published and form.is_active and form.deleted_at is None:
                return form
        base = select(BookingForm).options(selectinload(BookingForm.fields)).where(BookingForm.organization_id == self.org.id, BookingForm.is_published.is_(True), BookingForm.is_active.is_(True), BookingForm.deleted_at.is_(None), BookingForm.is_template.is_(False))
        if branch:
            f = self.db.scalars(base.where(BookingForm.scope == "branch", BookingForm.branch_id == branch.id).order_by(BookingForm.version.desc())).first()
            if f:
                return f
        return self.db.scalars(base.where(BookingForm.scope == "organization").order_by(BookingForm.updated_at.desc())).first()

    # --------------------------------------------------------- validation
    def validate_answers(self, form: BookingForm, answers: dict[str, Any] | None) -> dict[str, Any]:
        answers = dict(answers or {})
        fields = sorted(form.fields, key=lambda f: f.sort_order)
        known = {f.key for f in fields}
        errors: list[dict[str, str]] = []
        cleaned: dict[str, Any] = {}
        for f in fields:
            if not self.is_visible(f, answers):
                continue
            value = answers.get(f.key)
            empty = value is None or value == "" or value == [] or (f.field_type == "checkbox" and value is False)
            if empty:
                if f.is_required:
                    errors.append({"field": f.key, "message": f"{f.label} is required."})
                continue
            try:
                cleaned[f.key] = self._coerce(f, value)
            except ValueError as exc:
                errors.append({"field": f.key, "message": str(exc)})
        extra = set(answers) - known
        if extra:
            errors.append({"field": ",".join(sorted(extra)), "message": "Unknown field(s)."})
        if errors:
            raise ValidationFailed("Please correct the highlighted answers.", code="form_invalid", errors=errors)
        return cleaned

    @staticmethod
    def is_visible(field: BookingFormField, answers: dict[str, Any]) -> bool:
        for cond in field.conditions or []:
            c = FieldCondition(**cond)
            actual = answers.get(c.field)
            op = c.operator
            if op == "equals" and actual != c.value:
                return False
            if op == "not_equals" and actual == c.value:
                return False
            if op == "in" and actual not in (c.value or []):
                return False
            if op == "not_in" and actual in (c.value or []):
                return False
            if op == "is_true" and actual is not True:
                return False
            if op == "is_false" and actual is not False:
                return False
            if op == "is_empty" and actual not in (None, "", []):
                return False
            if op == "is_not_empty" and actual in (None, "", []):
                return False
            try:
                if op == "gt" and not (float(actual) > float(c.value)):
                    return False
                if op == "lt" and not (float(actual) < float(c.value)):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    @staticmethod
    def _coerce(f: BookingFormField, value: Any) -> Any:
        v = f.validation or {}
        t = f.field_type
        if t in ("text", "textarea", "email", "mobile"):
            if not isinstance(value, str):
                raise ValueError(f"{f.label} must be text.")
            s = value.strip()
            if v.get("min_length") and len(s) < v["min_length"]:
                raise ValueError(f"{f.label} must be at least {v['min_length']} characters.")
            if v.get("max_length") and len(s) > v["max_length"]:
                raise ValueError(f"{f.label} must be at most {v['max_length']} characters.")
            if v.get("regex") and not re.fullmatch(v["regex"], s):
                raise ValueError(v.get("regex_message") or f"{f.label} has an invalid format.")
            if t == "email":
                return normalize_email(s)
            if t == "mobile":
                return normalize_mobile(s)
            return s
        if t == "number":
            try:
                n = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{f.label} must be a number.") from exc
            if v.get("min") is not None and n < v["min"]:
                raise ValueError(f"{f.label} must be at least {v['min']}.")
            if v.get("max") is not None and n > v["max"]:
                raise ValueError(f"{f.label} must be at most {v['max']}.")
            return int(n) if n.is_integer() else n
        if t == "checkbox":
            if not isinstance(value, bool):
                raise ValueError(f"{f.label} must be true or false.")
            return value
        if t in ("dropdown", "radio"):
            allowed = {o["value"] for o in (f.options or [])}
            if value not in allowed:
                raise ValueError(f"{f.label}: choose one of the listed options.")
            return value
        if t == "multi_select":
            if not isinstance(value, list):
                raise ValueError(f"{f.label} must be a list.")
            allowed = {o["value"] for o in (f.options or [])}
            bad = [x for x in value if x not in allowed]
            if bad:
                raise ValueError(f"{f.label}: invalid option(s) {', '.join(map(str, bad))}.")
            return list(dict.fromkeys(value))
        if t == "date":
            try:
                d = date.fromisoformat(str(value))
            except ValueError as exc:
                raise ValueError(f"{f.label} must be a date (YYYY-MM-DD).") from exc
            for bound, cmp in (("min_date", lambda a, b: a < b), ("max_date", lambda a, b: a > b)):
                if v.get(bound):
                    limit = date.today() if v[bound] == "today" else date.fromisoformat(v[bound])
                    if cmp(d, limit):
                        raise ValueError(f"{f.label} is outside the allowed range.")
            return d.isoformat()
        if t == "file":
            files = value if isinstance(value, list) else [value]
            if not all(isinstance(x, dict) and isinstance(x.get("key"), str) and x["key"].startswith("private/") for x in files):
                raise ValueError(f"{f.label}: upload the file(s) first.")
            if v.get("max_files") and len(files) > v["max_files"]:
                raise ValueError(f"{f.label}: at most {v['max_files']} file(s).")
            return [{"key": x["key"], "name": str(x.get("name", ""))[:160], "mime_type": str(x.get("mime_type", ""))[:64], "size_bytes": int(x.get("size_bytes", 0))} for x in files]
        raise ValueError(f"Unsupported field type {t}.")

    # ---------------------------------------------------------- responses
    def record_response(self, form: BookingForm, answers: dict[str, Any], *, appointment: Appointment | None, customer: Customer | None) -> BookingFormResponse:
        attachments = [x for f in form.fields if f.field_type == "file" for x in (answers.get(f.key) or [])]
        row = BookingFormResponse(organization_id=self.org.id, form_id=form.id, appointment_id=appointment.id if appointment else None, customer_id=customer.id if customer else None,
                                  answers=seal_answers(form, answers), attachments=attachments or None, submitted_by_user_id=self.actor.id if self.actor else None)
        self.db.add(row)
        self.db.flush()
        return row

    def response_for_appointment(self, appointment: Appointment, *, show_sensitive: bool = False) -> FormResponseRead | None:
        row = self.db.scalar(select(BookingFormResponse).where(BookingFormResponse.appointment_id == appointment.id).order_by(BookingFormResponse.id.desc()))
        if row is None:
            return None
        form = self.db.get(BookingForm, row.form_id)
        cust = ids_to_public(self.db, Customer, {row.customer_id}).get(row.customer_id) if row.customer_id else None
        return FormResponseRead(id=row.public_id, form_id=form.public_id, form_name=form.name, form_version=form.version, appointment_id=appointment.public_id, customer_id=cust,
                                answers=open_answers(row.answers, show_sensitive), attachments=row.attachments, created_at=row.created_at)

    # --------------------------------------------------------- serialize
    def to_read(self, form: BookingForm) -> BookingFormRead:
        service_count = self.db.scalar(select(func.count()).select_from(Service).where(Service.booking_form_id == form.id, Service.deleted_at.is_(None))) or 0
        response_count = self.db.scalar(select(func.count()).select_from(BookingFormResponse).where(BookingFormResponse.form_id == form.id)) or 0
        branch = ids_to_public(self.db, Branch, {form.branch_id}).get(form.branch_id) if form.branch_id else None
        return BookingFormRead(
            id=form.public_id, slug=form.slug, name=form.name, version=form.version, description=form.description, instructions=form.instructions, scope=form.scope,
            branch_id=branch, settings=form.settings, is_template=form.is_template, is_published=form.is_published, is_active=form.is_active,
            fields=[self.field_read(f) for f in sorted(form.fields, key=lambda x: x.sort_order)], service_count=int(service_count), response_count=int(response_count),
            created_at=form.created_at, updated_at=form.updated_at,
        )

    def field_read(self, f: BookingFormField) -> FormFieldRead:
        return FormFieldRead(id=f.public_id, **self._field_input(f).model_dump())

    def public_form(self, form: BookingForm) -> PublicForm:
        return PublicForm(id=form.public_id, name=form.name, version=form.version, description=form.description, instructions=form.instructions,
                          fields=[self.field_read(f) for f in sorted(form.fields, key=lambda x: x.sort_order)])
