# Website integration (WordPress, Wix, HTML, React)

Everything is on **Admin → Booking page & Shopify → Add booking to Shopify or your website**. The code contains only your
public booking address, never a key or password. Shopify: [shopify-integration.md](shopify-integration.md).

## Preselection and tracking

Booking links can preselect a branch, doctor, service and date (`?branch=…&doctor=…&service=…&date=YYYY-MM-DD`) and carry
campaign values (`utm_source`, `utm_medium`, `utm_campaign`). Preselection only helps the visitor: prices and
availability are always checked on the server. Booking source and campaign are saved on the appointment and shown in
Admin → Website analytics.

## Options

| Site | How |
|---|---|
| Any HTML site, email, Linktree | "Any website link": a styled link button |
| WordPress | Custom HTML block with the button; or Embed (iframe) code; or a menu Custom Link |
| Wix | Button → Link → Web address; or Embed HTML with the iframe code (height ≥ 900 px) |
| React / Next.js | "React / Next.js" tab: `BookAppointmentButton` (link) and `BookingWidget` (iframe that resizes itself) |
| Optional iframe widget | "Embed (iframe)": add your site under **Allowed websites** first; other sites cannot frame the page |

The iframe page sends `{type: "appointment-booking:resize", height}` to its parent; the snippets accept it only from the
booking site's own origin.
