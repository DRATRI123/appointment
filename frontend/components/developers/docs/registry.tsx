"use client";

import type { ComponentType } from "react";
import { AdminApiPage, EmbedPage, GoLivePage, PublicBookingPage, RecipesPage } from "./pages-more";
import { AppointmentsPage, AvailabilityPage, BookingFormsPage, CataloguePage, CustomersPage, PaymentsPage, ReportsPage } from "./pages-api";
import { AuthenticationPage, ConventionsPage, ErrorsPage, OverviewPage, QuickstartPage } from "./pages-start";
import { EventsPage, WebhooksPage } from "./pages-webhooks";

export interface DocPage { slug: string; title: string; summary: string; group: string; Body: ComponentType; keywords?: string }

export const DOC_PAGES: DocPage[] = [
  { slug: "overview", group: "Get started", title: "Introduction", summary: "What you can connect and which option to use.", Body: OverviewPage },
  { slug: "quickstart", group: "Get started", title: "Quickstart", summary: "Your first booking through the API in five minutes.", Body: QuickstartPage, keywords: "first call tutorial" },
  { slug: "authentication", group: "Get started", title: "API keys & scopes", summary: "Keys, scopes, IP allow-list, expiry, rate limits and rotation.", Body: AuthenticationPage, keywords: "auth bearer token security ip rate limit" },
  { slug: "conventions", group: "Get started", title: "Conventions", summary: "IDs, dates, money in paise, pagination, versioning and retries.", Body: ConventionsPage, keywords: "pagination timezone paise utc" },
  { slug: "errors", group: "Get started", title: "Errors", summary: "Status codes, error codes and how to handle them.", Body: ErrorsPage, keywords: "409 429 401 403 422" },
  { slug: "catalogue", group: "API reference", title: "Branches, services & doctors", summary: "Read your catalogue to get ids for booking.", Body: CataloguePage, keywords: "branches services professionals schedules categories packages" },
  { slug: "availability", group: "API reference", title: "Availability", summary: "Free days and free times.", Body: AvailabilityPage, keywords: "slots free times calendar" },
  { slug: "appointments", group: "API reference", title: "Appointments", summary: "Book, hold, reschedule, cancel, check in and complete.", Body: AppointmentsPage, keywords: "booking status cancel reschedule hold waitlist recurring" },
  { slug: "customers", group: "API reference", title: "Customers", summary: "Search, create and update patients and family members.", Body: CustomersPage, keywords: "patients contacts dependents" },
  { slug: "payments", group: "API reference", title: "Payments (read only)", summary: "Payment status for UPI and cash; only staff can verify.", Body: PaymentsPage, keywords: "upi utr verified" },
  { slug: "reports", group: "API reference", title: "Reports & analytics", summary: "Dashboard numbers and report rows for accounting or BI.", Body: ReportsPage, keywords: "dashboard daily summary revenue" },
  { slug: "booking-forms", group: "API reference", title: "Booking forms", summary: "Intake questions and the answers given.", Body: BookingFormsPage, keywords: "intake questions form answers" },
  { slug: "webhooks", group: "Webhooks", title: "Webhooks", summary: "Receive signed events, verify them, retries and testing.", Body: WebhooksPage, keywords: "signature hmac secret retries receiver" },
  { slug: "events", group: "Webhooks", title: "Event reference", summary: "Every event and its payload.", Body: EventsPage, keywords: "appointment.created payment.verified payload" },
  { slug: "public-booking", group: "Booking on your site", title: "Public booking API", summary: "Build your own booking app or kiosk. No key needed.", Body: PublicBookingPage, keywords: "otp verification hold mobile app kiosk" },
  { slug: "embed", group: "Booking on your site", title: "Links, embed & Shopify", summary: "Booking links, URL parameters, iframe and Shopify.", Body: EmbedPage, keywords: "iframe shopify utm whatsapp qr link" },
  { slug: "recipes", group: "Guides", title: "Recipes", summary: "CRM sync, no-code tools, call centre, accounting.", Body: RecipesPage, keywords: "zapier make n8n crm sheets" },
  { slug: "go-live", group: "Guides", title: "Go-live & troubleshooting", summary: "Checklist before going live and fixes for common problems.", Body: GoLivePage, keywords: "checklist problems help faq" },
  { slug: "admin-api", group: "Guides", title: "Managing keys & webhooks", summary: "The endpoints behind the Developers screen.", Body: AdminApiPage, keywords: "developer portal manage" },
];

export const DOC_GROUPS = Array.from(new Set(DOC_PAGES.map((p) => p.group)));
export const findDocPage = (slug: string) => DOC_PAGES.find((p) => p.slug === slug);
