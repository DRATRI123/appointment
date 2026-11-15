"use client";

import Link from "next/link";
import { buttonHref } from "@/lib/site-links";
import { cn } from "@/lib/utils";
import { safeHex, textOn } from "@/components/public-booking/brand";
import { SiteIcon } from "./icons";
import { useSite } from "./site-context";
import type { ButtonPosition, SiteButton } from "@/types/website";

const SIZE = { sm: "h-9 px-4 text-sm", md: "h-11 px-5 text-sm", lg: "h-12 px-6 text-base" } as const;

function colours(b: SiteButton): React.CSSProperties {
  const solid = b.style === "solid";
  const base = b.color === "custom" ? safeHex(b.custom_color) : null;
  if (base) return solid ? { background: base, color: textOn(base), borderColor: base } : { color: base, borderColor: base };
  switch (b.color) {
    case "secondary":
      return solid ? { background: "var(--site-secondary)", color: "var(--site-secondary-ink)", borderColor: "var(--site-secondary)" } : { color: "var(--site-secondary)", borderColor: "var(--site-secondary)" };
    case "dark":
      return solid ? { background: "#111827", color: "#fff", borderColor: "#111827" } : { color: "#111827", borderColor: "#111827" };
    case "light":
      return solid ? { background: "#ffffff", color: "#111827", borderColor: "#ffffff" } : { color: "#ffffff", borderColor: "#ffffff" };
    default:
      return solid ? { background: "var(--primary)", color: "var(--primary-foreground)", borderColor: "var(--primary)" } : { color: "var(--primary)", borderColor: "var(--primary)" };
  }
}

export function SiteButtonLink({ button, size = "md", className, onClick }: { button: SiteButton; size?: keyof typeof SIZE; className?: string; onClick?: () => void }) {
  const { links } = useSite();
  const link = buttonHref(button, links);
  if (!link || !button.visible) return null;
  const cls = cn(
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full border-2 font-semibold transition-all duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary)]",
    button.style === "link" ? "h-auto border-0 px-0 underline-offset-4 hover:underline" : cn(SIZE[size], "hover:-translate-y-0.5 hover:shadow-md motion-reduce:hover:translate-y-0"),
    button.style === "soft" && "border-transparent",
    className,
  );
  const style = button.style === "soft" ? { ...colours({ ...button, style: "outline" }), background: "color-mix(in oklab, currentColor 12%, transparent)" } : colours(button);
  const content = <><SiteIcon name={button.icon} className="size-4 shrink-0" />{button.label}</>;
  const newTab = link.newTab ? { target: "_blank", rel: "noopener noreferrer" } : {};
  if (link.external || link.href.startsWith("tel:") || link.href.startsWith("/media/")) {
    return <a href={link.href} className={cls} style={style} onClick={onClick} data-button={button.id} {...newTab}>{content}</a>;
  }
  return <Link href={link.href} className={cls} style={style} onClick={onClick} data-button={button.id} {...newTab}>{content}</Link>;
}

export function ButtonsAt({ position, size, className, buttonClassName, max }: { position: ButtonPosition; size?: keyof typeof SIZE; className?: string; buttonClassName?: string; max?: number }) {
  const { doc, links } = useSite();
  const buttons = doc.buttons.filter((b) => b.visible && b.positions.includes(position) && buttonHref(b, links)).slice(0, max);
  if (!buttons.length) return null;
  return <div className={cn("flex flex-wrap items-center gap-3", className)}>{buttons.map((b) => <SiteButtonLink key={b.id} button={b} size={size} className={buttonClassName} />)}</div>;
}
