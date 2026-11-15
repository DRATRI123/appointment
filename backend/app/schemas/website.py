"""The clinic website document: settings, theme, navigation, sections, buttons, pages and SEO.

One document per organization, stored as JSON with a draft and a published copy. Everything an admin can type is
validated here: lengths, allowed section types, colours, fonts from an allow-list, and links. Links are never free
HTML: a button stores its *kind* and a validated target, and the frontend builds the address. Rich text is a small
Markdown subset that the frontend renders without injecting HTML.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HEX = r"^#[0-9a-fA-F]{6}$"
SLUG = r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"
SECTION_ID = r"^[a-z0-9][a-z0-9-]{0,39}$"
FONTS = ("modern", "classic", "friendly", "system")  # curated stacks served from this site; no third-party font loads
ICONS = (
    "none", "calendar", "phone", "message-circle", "mail", "map-pin", "external-link", "file-text", "arrow-right",
    "stethoscope", "heart-pulse", "leaf", "shield-check", "clock", "star", "award", "users", "sparkles", "home",
)
RESERVED_PAGE_SLUGS = frozenset({"book", "bookings", "appointments", "embed", "p", "preview", "api", "media", "admin"})
MAX_DOCUMENT_BYTES = 400_000

Markdown = Annotated[str, Field(max_length=20_000)]
Color = Annotated[str, Field(pattern=HEX)]
Icon = Literal[ICONS]  # type: ignore[valid-type]
PublicId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]

_CONTROL = re.compile(r"[\x00-\x1f\x7f\s]")


def safe_https_url(value: str, *, allow_media: bool = True) -> str:
    """An absolute https URL without credentials or whitespace, or a path under this site's /media/."""
    value = value.strip()
    if not value:
        return value
    if len(value) > 500 or _CONTROL.search(value):
        raise ValueError("Enter a web address without spaces.")
    if allow_media and value.startswith("/media/") and ".." not in value:
        return value
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or "." not in parts.hostname:
        raise ValueError("Links must start with https://")
    if parts.username or parts.password:
        raise ValueError("Links cannot contain a user name or password.")
    return value


def safe_phone(value: str) -> str:
    value = value.strip()
    if value and not re.fullmatch(r"\+?[0-9][0-9 ()-]{5,19}", value):
        raise ValueError("Enter a phone number with digits only, e.g. +91 98250 12345.")
    return value


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Image(_Model):
    url: str = Field(default="", max_length=500)
    alt: str = Field(default="", max_length=160)
    caption: str = Field(default="", max_length=160)

    _url = field_validator("url")(lambda cls, v: safe_https_url(v))


# ---------------------------------------------------------------------------------------------------- buttons
ButtonKind = Literal["book", "call", "whatsapp", "contact", "services", "external", "url", "maps", "pdf", "page"]
ButtonPosition = Literal["header", "hero", "footer", "service_cards", "floating", "contact"]


class Button(_Model):
    id: str = Field(pattern=SECTION_ID)
    label: str = Field(min_length=1, max_length=60)
    kind: ButtonKind = "book"
    url: str = Field(default="", max_length=500)  # external, url, pdf, maps (optional override)
    page: str = Field(default="", max_length=64)  # custom page slug for kind=page
    phone: str = Field(default="", max_length=24)  # call / whatsapp; empty = website settings
    service: str = Field(default="", max_length=80)  # book: preselect service slug
    branch: str = Field(default="", max_length=80)  # book / maps: branch slug
    message: str = Field(default="", max_length=300)  # whatsapp: prefilled text
    style: Literal["solid", "outline", "soft", "link"] = "solid"
    color: Literal["primary", "secondary", "dark", "light", "custom"] = "primary"
    custom_color: str = Field(default="", max_length=7)
    icon: Icon = "none"
    new_tab: bool = False
    visible: bool = True
    positions: list[ButtonPosition] = Field(default_factory=list, max_length=6)

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        return safe_https_url(v)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return safe_phone(v)

    @field_validator("service", "branch")
    @classmethod
    def _slug(cls, v: str) -> str:
        if v and not re.fullmatch(r"^[a-z0-9][a-z0-9-]{0,79}$", v):
            raise ValueError("Use the web address name (letters, numbers and dashes).")
        return v

    @model_validator(mode="after")
    def _target(self) -> Button:
        if self.kind in ("external", "url") and not self.url:
            raise ValueError(f"Button “{self.label}” needs a web address.")
        if self.kind == "pdf":
            if not self.url:
                raise ValueError(f"Button “{self.label}” needs a PDF address or upload.")
            if not self.url.lower().split("?")[0].endswith(".pdf"):
                raise ValueError(f"Button “{self.label}” must link to a .pdf file.")
        if self.kind == "page" and not re.fullmatch(SLUG, self.page or "-"):
            raise ValueError(f"Button “{self.label}” must point to one of your pages.")
        if self.color == "custom" and not re.fullmatch(HEX, self.custom_color or ""):
            raise ValueError(f"Button “{self.label}”: choose a colour like #0f766e.")
        return self


# -------------------------------------------------------------------------------------------------- navigation
class NavItem(_Model):
    label: str = Field(min_length=1, max_length=40)
    kind: Literal["section", "page", "url", "book"] = "section"
    target: str = Field(default="", max_length=500)  # section id, page slug or https URL
    new_tab: bool = False

    @model_validator(mode="after")
    def _target(self) -> NavItem:
        if self.kind == "url":
            self.target = safe_https_url(self.target, allow_media=False)
            if not self.target:
                raise ValueError(f"Menu item “{self.label}” needs a web address.")
        elif self.kind in ("section", "page") and not re.fullmatch(SECTION_ID if self.kind == "section" else SLUG, self.target or "-"):
            raise ValueError(f"Menu item “{self.label}” must point to a section or page.")
        return self


class Header(_Model):
    sticky: bool = True
    show_logo: bool = True
    show_phone: bool = True
    nav: list[NavItem] = Field(default_factory=list, max_length=10)


class FooterColumn(_Model):
    title: str = Field(default="", max_length=60)
    links: list[NavItem] = Field(default_factory=list, max_length=10)


class Footer(_Model):
    about: str = Field(default="", max_length=600)
    columns: list[FooterColumn] = Field(default_factory=list, max_length=4)
    show_social: bool = True
    show_policies: bool = True
    show_branches: bool = True
    copyright: str = Field(default="", max_length=160)


# ------------------------------------------------------------------------------------------------- settings
class Social(_Model):
    facebook: str = ""
    instagram: str = ""
    youtube: str = ""
    x: str = ""
    linkedin: str = ""
    google: str = ""  # Google Business Profile / reviews

    @field_validator("*")
    @classmethod
    def _url(cls, v: str) -> str:
        return safe_https_url(v, allow_media=False)


class Settings(_Model):
    site_name: str = Field(default="", max_length=120)
    clinic_name: str = Field(default="", max_length=160)
    tagline: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=600)
    logo_url: str = Field(default="", max_length=500)
    favicon_url: str = Field(default="", max_length=500)
    primary_color: Color = "#0f766e"
    secondary_color: Color = "#14b8a6"
    background_color: Color = "#fbfaf7"
    font: Literal[FONTS] = "modern"  # type: ignore[valid-type]
    phone: str = Field(default="", max_length=24)
    email: str = Field(default="", max_length=160)
    whatsapp: str = Field(default="", max_length=24)
    address: str = Field(default="", max_length=300)
    social: Social = Field(default_factory=Social)

    _urls = field_validator("logo_url", "favicon_url")(lambda cls, v: safe_https_url(v))
    _phones = field_validator("phone", "whatsapp")(lambda cls, v: safe_phone(v))

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if v and not re.fullmatch(r"[^@\s<>\"']+@[^@\s<>\"']+\.[a-zA-Z]{2,}", v):
            raise ValueError("Enter a valid email address.")
        return v


class SEO(_Model):
    title: str = Field(default="", max_length=70)
    description: str = Field(default="", max_length=170)
    image_url: str = Field(default="", max_length=500)
    noindex: bool = False

    _url = field_validator("image_url")(lambda cls, v: safe_https_url(v))


# -------------------------------------------------------------------------------------------------- sections
class _Section(_Model):
    id: str = Field(pattern=SECTION_ID)
    enabled: bool = True
    heading: str = Field(default="", max_length=120)
    intro: str = Field(default="", max_length=600)
    background: Literal["default", "muted", "brand", "dark", "custom"] = "default"
    custom_background: str = Field(default="", max_length=7)

    @model_validator(mode="after")
    def _bg(self):
        if self.background == "custom" and not re.fullmatch(HEX, self.custom_background or ""):
            raise ValueError(f"Section “{self.heading or self.id}”: choose a background colour like #f5f5f4.")
        return self


class Stat(_Model):
    value: str = Field(min_length=1, max_length=16)
    label: str = Field(min_length=1, max_length=48)


class HeroSection(_Section):
    type: Literal["hero"] = "hero"
    eyebrow: str = Field(default="", max_length=60)
    image: Image = Field(default_factory=Image)
    layout: Literal["split", "full", "centered"] = "split"
    stats: list[Stat] = Field(default_factory=list, max_length=4)


class AboutSection(_Section):
    type: Literal["about"] = "about"
    body: Markdown = ""
    image: Image = Field(default_factory=Image)
    layout: Literal["image_left", "image_right", "text_only"] = "image_right"
    highlights: list[Stat] = Field(default_factory=list, max_length=6)


class DoctorsSection(_Section):
    type: Literal["doctors"] = "doctors"
    professional_ids: list[PublicId] = Field(default_factory=list, max_length=60)  # empty = everyone bookable online
    layout: Literal["grid", "list"] = "grid"
    show_fees: bool = False


class ServicesSection(_Section):
    type: Literal["services"] = "services"
    service_ids: list[PublicId] = Field(default_factory=list, max_length=100)
    category_ids: list[PublicId] = Field(default_factory=list, max_length=40)
    layout: Literal["cards", "list"] = "cards"
    show_prices: bool = True
    group_by_category: bool = True


class CategoriesSection(_Section):
    type: Literal["categories"] = "categories"
    category_ids: list[PublicId] = Field(default_factory=list, max_length=40)


class Feature(_Model):
    icon: Icon = "sparkles"
    title: str = Field(min_length=1, max_length=80)
    text: str = Field(default="", max_length=400)


class FeaturesSection(_Section):
    type: Literal["features"] = "features"  # facilities, "why choose us"
    items: list[Feature] = Field(default_factory=list, max_length=12)
    columns: Literal[2, 3, 4] = 3


class GallerySection(_Section):
    type: Literal["gallery"] = "gallery"
    images: list[Image] = Field(default_factory=list, max_length=40)
    layout: Literal["grid", "mosaic"] = "grid"


class Testimonial(_Model):
    id: str = Field(pattern=SECTION_ID)
    name: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=600)
    rating: int | None = Field(default=None, ge=1, le=5)
    context: str = Field(default="", max_length=80)  # e.g. "Panchakarma patient"
    received_on: date | None = None
    source: Literal["in_clinic", "google", "email", "whatsapp", "other"] = "in_clinic"
    consent: bool = False  # the patient agreed to it being published
    approved: bool = False


class TestimonialsSection(_Section):
    type: Literal["testimonials"] = "testimonials"
    items: list[Testimonial] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def _consent(self) -> TestimonialsSection:
        for t in self.items:
            if t.approved and not t.consent:
                raise ValueError(f"Testimonial from {t.name}: record the patient's consent before approving it.")
        return self


class FAQ(_Model):
    question: str = Field(min_length=1, max_length=200)
    answer: Annotated[str, Field(min_length=1, max_length=2000)]


class FAQSection(_Section):
    type: Literal["faq"] = "faq"
    items: list[FAQ] = Field(default_factory=list, max_length=40)


class BranchesSection(_Section):
    type: Literal["branches"] = "branches"
    branch_ids: list[PublicId] = Field(default_factory=list, max_length=40)
    show_hours: bool = True
    show_map: bool = True


class ContactSection(_Section):
    type: Literal["contact"] = "contact"
    show_phone: bool = True
    show_email: bool = True
    show_whatsapp: bool = True
    show_map: bool = True


class CTASection(_Section):
    type: Literal["cta"] = "cta"
    buttons: list[Button] = Field(default_factory=list, max_length=3)


class RichTextSection(_Section):
    type: Literal["text"] = "text"
    body: Markdown = ""
    width: Literal["narrow", "wide"] = "narrow"


Section = Annotated[
    HeroSection | AboutSection | DoctorsSection | ServicesSection | CategoriesSection | FeaturesSection | GallerySection
    | TestimonialsSection | FAQSection | BranchesSection | ContactSection | CTASection | RichTextSection,
    Field(discriminator="type"),
]
SECTION_TYPES = ("hero", "about", "doctors", "services", "categories", "features", "gallery", "testimonials", "faq",
                 "branches", "contact", "cta", "text")


class Page(_Model):
    slug: str = Field(pattern=SLUG)
    title: str = Field(min_length=1, max_length=120)
    body: Markdown = ""
    sections: list[Section] = Field(default_factory=list, max_length=20)
    enabled: bool = True
    show_in_nav: bool = False
    seo_title: str = Field(default="", max_length=70)
    seo_description: str = Field(default="", max_length=170)

    @field_validator("slug")
    @classmethod
    def _reserved(cls, v: str) -> str:
        if v in RESERVED_PAGE_SLUGS:
            raise ValueError(f"“{v}” is used by the booking site; choose another page address.")
        return v


class WebsiteDocument(_Model):
    version: Literal[1] = 1
    settings: Settings = Field(default_factory=Settings)
    header: Header = Field(default_factory=Header)
    sections: list[Section] = Field(default_factory=list, max_length=40)
    buttons: list[Button] = Field(default_factory=list, max_length=20)
    footer: Footer = Field(default_factory=Footer)
    pages: list[Page] = Field(default_factory=list, max_length=30)
    seo: SEO = Field(default_factory=SEO)

    @model_validator(mode="after")
    def _unique(self) -> WebsiteDocument:
        def dupes(values: list[str]) -> set[str]:
            seen: set[str] = set()
            return {v for v in values if v in seen or seen.add(v)}  # type: ignore[func-returns-value]

        if d := dupes([s.id for s in self.sections]):
            raise ValueError(f"Two sections share the id {sorted(d)[0]}.")
        if d := dupes([p.slug for p in self.pages]):
            raise ValueError(f"Two pages share the address {sorted(d)[0]}.")
        if d := dupes([b.id for b in self.buttons]):
            raise ValueError(f"Two buttons share the id {sorted(d)[0]}.")
        slugs = {p.slug for p in self.pages}
        for b in self.buttons + [b for s in self.sections if isinstance(s, CTASection) for b in s.buttons]:
            if b.kind == "page" and b.page not in slugs:
                raise ValueError(f"Button “{b.label}” points to a page that does not exist.")
        return self


# ------------------------------------------------------------------------------------------------- API models
class WebsiteState(BaseModel):
    draft: WebsiteDocument
    published: WebsiteDocument | None
    lock_version: int
    published_version: int
    published_at: datetime | None
    draft_updated_at: datetime | None
    has_unpublished_changes: bool
    public_url_path: str


class DraftUpdate(BaseModel):
    # Validated by the service (not here) so errors come back as one readable message with code website_invalid.
    document: dict[str, Any]
    lock_version: int = Field(ge=0, description="The lock_version you loaded; a newer save by someone else returns 409")


class PublishRequest(BaseModel):
    note: str = Field(default="", max_length=200)
    lock_version: int = Field(ge=0)


class WebsiteVersionRead(BaseModel):
    version: int
    published_at: datetime
    published_by: str | None
    note: str | None


class PublicWebsite(BaseModel):
    document: WebsiteDocument
    published: bool  # False: generated from the clinic profile because nothing has been published yet
    version: int
