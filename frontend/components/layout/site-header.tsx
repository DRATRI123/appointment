import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Logo } from "./logo";

const nav = [
  { href: "/#features", label: "Features" },
  { href: "/#payments", label: "UPI payments" },
  { href: "/#roadmap", label: "Roadmap" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 w-full border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <Logo />
        <nav className="hidden items-center gap-6 text-sm text-muted-foreground md:flex">
          {nav.map((item) => (
            <Link key={item.href} href={item.href} className="transition-colors hover:text-foreground">
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href="/login">Sign in</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/admin">Admin</Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
