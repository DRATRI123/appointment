import Link from "next/link";
import { ArrowRight, Building2, CalendarClock, QrCode, ShieldCheck, Stethoscope, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SystemStatus } from "@/components/system-status";

const features = [
  {
    icon: Building2,
    title: "Multi-organization, multi-branch",
    body: "Clinics, hospitals, Ayurvedic centres, salons and consultants each get isolated data, branding and settings.",
  },
  {
    icon: Stethoscope,
    title: "Professionals and services",
    body: "Doctors and professionals work across branches with separate fees, schedules, leaves and buffer times.",
  },
  {
    icon: CalendarClock,
    title: "Double-booking-proof scheduling",
    body: "Transactional slot holds, database-level unique constraints and timezone-aware availability.",
  },
  {
    icon: QrCode,
    title: "Own UPI QR payments",
    body: "Dynamic UPI QR codes to your own UPI ID. No Razorpay, Stripe or gateway fees. Staff verify UTRs before confirmation.",
  },
  {
    icon: Users,
    title: "Customers and family members",
    body: "Patient profiles, dependents, documents, notes and consent with strict clinical access controls.",
  },
  {
    icon: ShieldCheck,
    title: "Security by design",
    body: "Argon2 hashing, rotating refresh tokens, RBAC, tenant guards, audit logs and rate limiting.",
  },
];

const roadmap = [
  ["1", "Architecture, database schema, migrations, environment", "done"],
  ["2", "Authentication, users, organizations, RBAC", "next"],
  ["3", "Branches, professionals, services", ""],
  ["4", "Scheduling engine, availability, booking", ""],
  ["5", "Customers and booking form builder", ""],
  ["6", "Own UPI QR payments and verification dashboard", ""],
  ["7", "Refunds and bank reconciliation", ""],
  ["8", "Notifications: email, SMS, WhatsApp", ""],
  ["9", "Google Calendar and video consultations", ""],
  ["10", "Admin dashboards and analytics", ""],
  ["11", "Developer API and webhooks", ""],
  ["12", "Security hardening and full testing", ""],
  ["13", "Production deployment and monitoring", ""],
  ["14", "PostgreSQL migration and performance", ""],
] as const;

export default function HomePage() {
  return (
    <div className="mx-auto max-w-6xl px-4">
      <section className="grid items-center gap-10 py-16 md:grid-cols-[1.2fr_1fr] md:py-24">
        <div className="space-y-6">
          <Badge variant="secondary" className="gap-1.5">
            <span className="size-1.5 rounded-full bg-success" /> Phase 1 foundation ready
          </Badge>
          <h1 className="text-4xl font-semibold leading-tight tracking-tight md:text-6xl">
            Appointment booking that pays straight into <span className="text-primary">your UPI account</span>.
          </h1>
          <p className="max-w-xl text-lg text-muted-foreground">
            A production-grade, multi-tenant platform for doctors, clinics, wellness centres and independent
            professionals. Online booking, staff dashboards, reminders and reports, with payments verified by your
            team rather than a third-party gateway.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/admin">
                Open admin dashboard <ArrowRight />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/customer">Customer dashboard</Link>
            </Button>
          </div>
        </div>
        <SystemStatus />
      </section>

      <section id="features" className="py-12">
        <h2 className="text-2xl font-semibold tracking-tight">Everything an appointment business needs</h2>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <Card key={f.title} className="gap-3 py-5 transition-shadow hover:shadow-md">
              <CardHeader>
                <span className="grid size-9 place-items-center rounded-lg bg-accent text-accent-foreground">
                  <f.icon className="size-4" />
                </span>
                <CardTitle className="pt-2">{f.title}</CardTitle>
                <CardDescription>{f.body}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      </section>

      <section id="payments" className="py-12">
        <Card className="overflow-hidden border-primary/20 bg-linear-to-br from-accent/60 to-background">
          <CardContent className="grid gap-8 md:grid-cols-2">
            <div className="space-y-4">
              <h2 className="text-2xl font-semibold tracking-tight">How own-UPI payments work</h2>
              <ol className="space-y-3 text-sm text-muted-foreground">
                {[
                  "Backend computes the payable amount in paise and picks the right UPI account.",
                  "A dynamic QR encodes upi://pay with your UPI ID, merchant name, amount and a unique reference.",
                  "The customer pays in Google Pay, PhonePe, Paytm or BHIM and submits the UTR and screenshot.",
                  "Authorized staff verify the bank credit, then the appointment is confirmed and notifications go out.",
                  "Bank statement CSV reconciliation and manual, proof-backed refunds close the loop.",
                ].map((step, i) => (
                  <li key={step} className="flex gap-3">
                    <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                      {i + 1}
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
            <div className="flex items-center justify-center">
              <div className="rounded-2xl border bg-card p-6 text-center shadow-sm">
                <div className="mx-auto grid size-40 place-items-center rounded-xl bg-muted">
                  <QrCode className="size-20 text-muted-foreground" />
                </div>
                <p className="mt-4 font-mono text-xs text-muted-foreground">upi://pay?pa=clinic@upi&amp;am=500.00&amp;tn=PAY-…</p>
                <p className="mt-1 text-xs text-muted-foreground">A QR is a payment request, never proof of payment.</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      <section id="roadmap" className="py-12">
        <h2 className="text-2xl font-semibold tracking-tight">Delivery roadmap</h2>
        <p className="mt-1 text-muted-foreground">Each phase is implemented, tested and documented before the next begins.</p>
        <div className="mt-6 grid gap-2 sm:grid-cols-2">
          {roadmap.map(([phase, label, state]) => (
            <div key={phase} className="flex items-center gap-3 rounded-lg border px-3 py-2 text-sm">
              <span className="grid size-7 place-items-center rounded-md bg-muted font-mono text-xs">{phase}</span>
              <span className="flex-1">{label}</span>
              {state === "done" ? <Badge variant="success">Done</Badge> : state === "next" ? <Badge variant="secondary">Next</Badge> : null}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
