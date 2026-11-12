"use client";

import Link from "next/link";
import { CalendarClock } from "lucide-react";
import { useOrg } from "../org-provider";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";

export default function BookPlaceholder() {
  const { slug } = useOrg();
  return (
    <EmptyState
      icon={CalendarClock}
      title="Online booking opens in Phase 4"
      body="The scheduling engine (availability, slot holds and the booking wizard) is the next phase. The catalogue you see here is already live."
      action={<Button asChild variant="outline"><Link href={`/o/${slug}`}>Back to services</Link></Button>}
    />
  );
}
