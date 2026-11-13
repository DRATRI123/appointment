import Link from "next/link";
import { CalendarCheck2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function Logo({ className, href = "/", labelClassName }: { className?: string; href?: string; labelClassName?: string }) {
  return (
    <Link href={href} className={cn("flex items-center gap-2 font-semibold tracking-tight", className)}>
      <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
        <CalendarCheck2 className="size-4" />
      </span>
      <span className={labelClassName}>Appointment Platform</span>
    </Link>
  );
}
