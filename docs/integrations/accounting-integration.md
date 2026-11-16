# Accounting: Zoho Books and Tally

Only **verified** payments and **processed** refunds are ever sent. Submitted, rejected or expired payments never are.
This app stays the record of what was verified; accounting gets a copy.

## Zoho Books

1. A Zoho server-based application (see [crm-integration.md](crm-integration.md)) with the Zoho Books scopes.
2. Admin → Integrations → **Zoho Books**: data centre, client ID, secret → Save → **Connect Zoho account**. The first
   organization is picked; change "Zoho Books organization ID" if you have several. Optional: "Account ID for refunds".
3. Needs `payments:verify`.

What happens for each verified payment: the patient becomes a Zoho Books contact (name with the patient code, because
Zoho needs unique contact names) → an **invoice** (service, amount in rupees, appointment reference) → a **customer
payment** applied to it (mode UPI / Cash / Bank Transfer, UTR as reference, date in the clinic's time zone). Each id is
stored as soon as Zoho returns it, so a retry after a failure never creates a second invoice.

Refunds: Zoho Books documents refunds of customer payments only for online card payments ("autotransaction"), so a
refund becomes a **credit note**, plus a credit-note refund from the account you set.

Taxes (GST) are not added: set tax rules in Zoho Books if needed.

## Tally (XML file)

Tally has no cloud API. Admin → Integrations → **Tally**: ledger names (UPI/bank, cash, income), company name → Save →
Test → **Download XML** for a date range. In Tally: **Gateway of Tally → Import → Vouchers**.

* Verified payment = **Receipt** voucher (Dr bank or cash, Cr income). Processed refund = **Payment** voucher.
* Each voucher carries the payment's id as `REMOTEID`. Payments already exported are left out of the next file unless
  "Include vouchers exported before" is ticked (re-importing them may create duplicates in Tally).
* Branch-limited staff export their branch only. Exports need "confirm it is you" and count toward the daily export limit.

## Reports

Daily collections: Admin → Reports → *Daily summary* and *Payments* (filter by branch); bank matching: Admin → Reconciliation.
