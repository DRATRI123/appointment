"use client";

import Link from "next/link";
import { useAuth } from "@/components/auth/auth-provider";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";

export default function CustomerHome() {
  const { user } = useAuth();
  return (
    <div className="space-y-8">
      <PageHeader title={`Hello, ${user?.full_name ?? ""}`} description="Your bookings and payments will appear here." actions={<Button asChild variant="outline"><Link href="/customer/profile">Profile &amp; security</Link></Button>} />
      <div className="flex flex-wrap gap-3">
        <Button asChild><Link href="/customer/appointments">My appointments</Link></Button>
        <Button asChild variant="outline"><Link href="/customer/family">Family &amp; preferences</Link></Button>
      </div>
      <Button asChild variant="outline" className="w-fit"><Link href="/customer/payments">Payments</Link></Button>
    </div>
  );
}
