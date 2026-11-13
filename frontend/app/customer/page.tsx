"use client";

import Link from "next/link";
import { useAuth } from "@/components/auth/auth-provider";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";
import { Button } from "@/components/ui/button";

export default function CustomerHome() {
  const { user } = useAuth();
  return (
    <div className="space-y-8">
      <PageHeader title={`Hello, ${user?.full_name ?? ""}`} description="Your bookings and payments will appear here." actions={<Button asChild variant="outline"><Link href="/customer/profile">Profile &amp; security</Link></Button>} />
      <div className="flex flex-wrap gap-3">
        <Button asChild><Link href="/customer/appointments">My appointments</Link></Button>
      </div>
      <PhasePlaceholder
        title="Coming next"
        description="Payment receipts, family profiles and saved professionals."
        phase={5}
        items={["Payment receipts", "Family member profiles", "Saved professionals and branches", "Documents"]}
      />
    </div>
  );
}
