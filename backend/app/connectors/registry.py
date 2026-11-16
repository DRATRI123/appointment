"""The connector catalogue. Settings use the same field definitions as the super admin panel (secrets encrypted)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.platform_config import F

ZOHO_DATA_CENTERS = ("in", "com", "eu", "com.au", "jp", "ca", "sa")
RETRIES = F("max_attempts", "Retries before giving up", "number", help="1–20 tries with growing waits (1 min, 5 min, 30 min, 2 h, 6 h …)")


@dataclass(frozen=True)
class Connector:
    key: str
    name: str
    category: str  # google | email | whatsapp | sms | automation | shopify | website | crm | accounting | storage | analytics | api | webhooks
    description: str
    auth: str  # google (OAuth) | zoho (OAuth) | fields (keys typed in) | none
    adapter: str  # "module:Class"
    fields: tuple[F, ...] = ()
    defaults: dict[str, Any] = field(default_factory=dict)
    scopes: tuple[str, ...] = ()
    syncs: tuple[str, ...] = ()  # entity types the sync queue pushes
    docs: str = ""
    privacy: str = ""  # what leaves the platform, shown before connecting
    permission: str = "integrations:write"


CONNECTORS: dict[str, Connector] = {c.key: c for c in (
    Connector("gmail", "Gmail", "email", "Send the clinic's emails (confirmations, reminders, sign-in codes) from your own Gmail or "
              "Google Workspace address.", "google", "app.connectors.google:Gmail",
              fields=(F("use_for_all", "Send all clinic emails through Gmail", "bool", help="Off: Gmail is used only for test emails"),),
              defaults={"use_for_all": True}, scopes=("https://www.googleapis.com/auth/gmail.send",),
              docs="docs/integrations/gmail-integration.md",
              privacy="Email text goes to Google to be delivered. Google limits sending (about 2,000 a day for Workspace, 500 for gmail.com)."),
    Connector("google_contacts", "Google Contacts", "google", "Keep patients' names, numbers and emails in the clinic's Google Contacts "
              "(one contact per patient, duplicates matched by number or email).", "google", "app.connectors.google:Contacts",
              fields=(F("include_mobile", "Include mobile numbers", "bool"), F("include_email", "Include emails", "bool"), RETRIES),
              defaults={"include_mobile": True, "include_email": True, "max_attempts": 8},
              scopes=("https://www.googleapis.com/auth/contacts",), syncs=("customer",), docs="docs/integrations/google-integration.md",
              privacy="Only name, mobile and email. Never notes, documents, form answers or payments."),
    Connector("google_drive", "Google Drive", "storage", "Keep a copy of each patient document in a private folder of the clinic's Google "
              "Drive. Nothing is shared: the folder is visible only to the connected account.", "google", "app.connectors.google:Drive",
              fields=(F("folder_name", "Folder name", help="Created on the first upload"), RETRIES),
              defaults={"folder_name": "Patient documents", "max_attempts": 8},
              scopes=("https://www.googleapis.com/auth/drive.file",), syncs=("document",), docs="docs/integrations/google-integration.md",
              privacy="Patient documents are copied (readable) to the connected Google account. Access in this app still needs clinical permission.",
              permission="customers:clinical_write"),
    Connector("n8n", "n8n automation", "automation", "Send booking, patient and payment events to your n8n workflows, and let approved "
              "workflows send notifications, create follow-up tasks and read appointment details.", "fields", "app.connectors.n8n:N8n",
              fields=(F("url", "n8n Webhook URL", required=True, help="The Production URL of your n8n Webhook node (https://…)"),
                      F("events", "Events to send", help="Comma-separated, or * for all. Example: appointment.confirmed, payment.verified"),
                      F("allowed_actions", "Actions n8n may perform", help="Comma-separated: send_notification, create_follow_up, "
                        "trigger_reminder, get_appointment, update_customer"), RETRIES),
              defaults={"events": "*", "allowed_actions": "get_appointment, create_follow_up", "max_attempts": 8},
              docs="docs/integrations/n8n-integration.md",
              privacy="Event data: booking times, service, doctor, patient name and contact. Never notes, documents or form answers."),
    Connector("hubspot", "HubSpot", "crm", "Create and update a HubSpot contact for every patient, and optionally log appointments on the "
              "contact's timeline.", "fields", "app.connectors.crm:HubSpot",
              fields=(F("access_token", "Private app access token", "secret", required=True, help="HubSpot → Settings → Integrations → Private apps. "
                        "Scopes: crm.objects.contacts.read, crm.objects.contacts.write"),
                      F("include_mobile", "Send mobile numbers", "bool"), F("include_email", "Send emails", "bool"), F("include_city", "Send city", "bool"),
                      F("log_appointments", "Log appointments as notes", "bool"), RETRIES),
              defaults={"include_mobile": True, "include_email": True, "include_city": False, "log_appointments": False, "max_attempts": 8},
              syncs=("customer", "appointment"), docs="docs/integrations/crm-integration.md",
              privacy="Only the fields you tick. Never clinical notes, documents or form answers."),
    Connector("zoho_crm", "Zoho CRM", "crm", "Create and update a Zoho CRM contact for every patient (matched by email or phone), and "
              "optionally add appointment notes.", "zoho", "app.connectors.crm:ZohoCRM",
              fields=(F("data_center", "Zoho data centre", "choice", ZOHO_DATA_CENTERS, required=True, help="in = India (zoho.in), com = US …"),
                      F("client_id", "Client ID", required=True, help="Zoho API Console → Server-based application"),
                      F("client_secret", "Client secret", "secret", required=True),
                      F("include_mobile", "Send mobile numbers", "bool"), F("include_email", "Send emails", "bool"), F("include_city", "Send city", "bool"),
                      F("log_appointments", "Add appointment notes", "bool"), RETRIES),
              defaults={"data_center": "in", "include_mobile": True, "include_email": True, "include_city": False, "log_appointments": False, "max_attempts": 8},
              scopes=("ZohoCRM.modules.contacts.ALL", "ZohoCRM.modules.notes.ALL", "ZohoCRM.users.READ"),
              syncs=("customer", "appointment"), docs="docs/integrations/crm-integration.md",
              privacy="Only the fields you tick. Never clinical notes, documents or form answers."),
    Connector("zoho_books", "Zoho Books", "accounting", "Send verified payments as invoices with payments, and refunds as credit notes. "
              "Unverified or rejected payments are never sent.", "zoho", "app.connectors.accounting:ZohoBooks",
              fields=(F("data_center", "Zoho data centre", "choice", ZOHO_DATA_CENTERS, required=True),
                      F("client_id", "Client ID", required=True), F("client_secret", "Client secret", "secret", required=True),
                      F("organization_id", "Zoho Books organization ID", help="Filled in after connecting; change it if you have several"),
                      F("refund_account_id", "Account ID for refunds (optional)", help="Bank or cash account the refunds are paid from"),
                      RETRIES),
              defaults={"data_center": "in", "max_attempts": 8},
              scopes=("ZohoBooks.contacts.ALL", "ZohoBooks.invoices.ALL", "ZohoBooks.customerpayments.ALL", "ZohoBooks.creditnotes.ALL",
                      "ZohoBooks.settings.READ"),
              syncs=("payment", "refund"), docs="docs/integrations/accounting-integration.md",
              privacy="Patient name and contact, service, amount, date and reference. Nothing clinical.", permission="payments:verify"),
    Connector("tally", "Tally (XML export)", "accounting", "Download verified payments and refunds as a Tally import file (receipt and "
              "payment vouchers). Importing the same file twice updates the vouchers instead of duplicating them.", "none",
              "app.connectors.accounting:Tally",
              fields=(F("company_name", "Tally company name", help="Exactly as in Tally (optional)"),
                      F("bank_ledger", "Ledger for UPI / bank payments", required=True), F("cash_ledger", "Ledger for cash payments", required=True),
                      F("income_ledger", "Income ledger", required=True), F("party_ledger", "Patient ledger", help="One ledger for all patients, e.g. Patients")),
              defaults={"bank_ledger": "Bank Account", "cash_ledger": "Cash", "income_ledger": "Consultation Fees", "party_ledger": "Patients"},
              docs="docs/integrations/accounting-integration.md", permission="payments:verify"),
    Connector("ga4", "Google Analytics 4 / Tag Manager", "analytics", "Measure booking page visits, booking starts, completed and abandoned "
              "bookings and where visitors came from. Loads only after the visitor agrees.", "none", "app.connectors.analytics:Analytics",
              fields=(F("measurement_id", "GA4 measurement ID", help="G-XXXXXXXXXX"), F("gtm_container_id", "Tag Manager container ID", help="GTM-XXXXXXX (optional)")),
              docs="docs/integrations/analytics-integration.md",
              privacy="Page views and booking steps only. Never names, numbers, notes or what the visit is for."),
)}


def get(key: str) -> Connector | None:
    return CONNECTORS.get(key)


def syncing(entity_type: str) -> list[str]:
    return [c.key for c in CONNECTORS.values() if entity_type in c.syncs]
