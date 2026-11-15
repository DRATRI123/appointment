"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarCheck2, House, Phone, Stethoscope } from "lucide-react";
import { phoneDigits } from "@/lib/site-links";
import { cn } from "@/lib/utils";
import { useSite } from "./site-context";

/** App-style tab bar on phones for the booking pages: Home · Doctors · My bookings · Call. */
export function BottomNav() {
  const { base, doc } = useSite();
  const pathname = usePathname();
  const phone = doc.settings.phone;
  const items = [
    { href: base, label: "Home", icon: House, active: pathname === base },
    { href: `${base}/book`, label: "Doctors", icon: Stethoscope, active: pathname.startsWith(`${base}/book`) },
    { href: `${base}/bookings`, label: "My bookings", icon: CalendarCheck2, active: pathname.startsWith(`${base}/bookings`) || pathname.startsWith(`${base}/appointments`) },
  ];
  return (
    <nav aria-label="App" className="fixed inset-x-3 bottom-3 z-30 rounded-full border border-black/5 bg-white/95 p-1.5 shadow-[0_10px_30px_-10px_rgb(0_0_0/0.35)] backdrop-blur md:hidden" data-testid="bottom-nav">
      <ul className="flex items-center justify-between">
        {items.map(({ href, label, icon: Icon, active }) => (
          <li key={label} className="flex-1">
            <Link href={href} aria-current={active ? "page" : undefined}
              className={cn("flex h-11 items-center justify-center gap-1.5 rounded-full text-xs font-semibold transition-colors", active ? "bg-[var(--primary)] text-[var(--primary-foreground)]" : "text-gray-600 hover:text-gray-900")}>
              <Icon className="size-5" aria-hidden />{active ? <span>{label}</span> : <span className="sr-only">{label}</span>}
            </Link>
          </li>
        ))}
        {phone ? (
          <li className="flex-1">
            <a href={`tel:${phoneDigits(phone)}`} className="flex h-11 items-center justify-center rounded-full text-gray-600 hover:text-gray-900"><Phone className="size-5" aria-hidden /><span className="sr-only">Call the clinic</span></a>
          </li>
        ) : null}
      </ul>
    </nav>
  );
}
