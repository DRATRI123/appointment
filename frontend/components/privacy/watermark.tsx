"use client";

import { useEffect, useMemo, useState } from "react";
import type { PrivacyPolicy } from "@/services/privacy";

function stamp(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * A faint, repeating, diagonal watermark over staff screens: account reference, clinic, time and session.
 * No name, email or number appears in it. It is decorative for assistive technology (aria-hidden), never takes
 * clicks or focus, and also appears on printouts. It deters and traces; it cannot prevent a screenshot.
 */
export function Watermark({ policy }: { policy: PrivacyPolicy }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(t);
  }, []);
  const text = `${policy.user_ref} · ${policy.organization_ref} · ${stamp(now)} · ${policy.session_ref}`;
  const background = useMemo(() => {
    const safe = text.replace(/[<>&"']/g, "");
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="420" height="220"><text x="10" y="150" transform="rotate(-24 210 110)" font-family="system-ui, sans-serif" font-size="15" fill="#64748b">${safe}</text></svg>`;
    return `url("data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}")`;
  }, [text]);
  return (
    <div
      aria-hidden
      data-watermark
      data-testid="watermark"
      data-text={text}
      className="pointer-events-none fixed inset-0 z-40 select-none print:fixed"
      style={{ backgroundImage: background, opacity: policy.watermark_opacity, printColorAdjust: "exact", WebkitPrintColorAdjust: "exact" }}
    />
  );
}
