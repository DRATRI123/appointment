import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 py-8 text-sm text-muted-foreground md:flex-row">
        <p>© {new Date().getFullYear()} Appointment Platform. Payments go directly to the organization&apos;s own UPI account.</p>
        <nav className="flex gap-4">
          <Link href="/privacy" className="hover:text-foreground">Privacy</Link>
          <Link href="/terms" className="hover:text-foreground">Terms</Link>
          <Link href="/refund-policy" className="hover:text-foreground">Cancellation &amp; refunds</Link>
        </nav>
      </div>
    </footer>
  );
}
