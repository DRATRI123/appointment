import type { CSSProperties } from "react";
import { safeHex, textOn } from "@/components/public-booking/brand";
import type { Font, SiteSettings } from "@/types/website";

/** Curated font stacks. "modern" is Geist (bundled with the app); the others use fonts already on the device. */
export const FONT_STACKS: Record<Font, { body: string; heading: string; label: string }> = {
  modern: { body: "var(--font-geist-sans), ui-sans-serif, system-ui, sans-serif", heading: "var(--font-geist-sans), ui-sans-serif, system-ui, sans-serif", label: "Modern (Geist)" },
  classic: { body: "var(--font-geist-sans), ui-sans-serif, system-ui, sans-serif", heading: "ui-serif, Georgia, 'Iowan Old Style', 'Palatino Linotype', serif", label: "Classic (serif headings)" },
  friendly: { body: "ui-rounded, 'SF Pro Rounded', 'Hiragino Maru Gothic ProN', Quicksand, Nunito, 'Segoe UI', system-ui, sans-serif", heading: "ui-rounded, 'SF Pro Rounded', 'Hiragino Maru Gothic ProN', Quicksand, Nunito, 'Segoe UI', system-ui, sans-serif", label: "Friendly (rounded)" },
  system: { body: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans', sans-serif", heading: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans', sans-serif", label: "Device default" },
};

/**
 * CSS variables that re-skin the whole public site (and the booking flow inside it) with the clinic's colours.
 * Text colours are chosen for contrast against each brand colour.
 */
export function siteTheme(settings: Pick<SiteSettings, "primary_color" | "secondary_color" | "background_color" | "font">): CSSProperties {
  const primary = safeHex(settings.primary_color, "#0f766e");
  const secondary = safeHex(settings.secondary_color, "#14b8a6");
  const background = safeHex(settings.background_color, "#fbfaf7");
  const font = FONT_STACKS[settings.font] ?? FONT_STACKS.modern;
  return {
    "--primary": primary,
    "--primary-foreground": textOn(primary),
    "--ring": primary,
    "--site-secondary": secondary,
    "--site-secondary-ink": textOn(secondary),
    "--site-bg": background,
    "--site-heading-font": font.heading,
    fontFamily: font.body,
    background,
  } as CSSProperties;
}
