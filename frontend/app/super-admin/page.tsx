import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata = { title: "Platform overview" };

export default function Page() {
  return (
    <PhasePlaceholder
      title="Platform overview"
      description="Onboard, activate and suspend organizations; monitor usage, jobs and system health."
      phase={10}
      items={["Organization onboarding and status", "Subscription plans", "Platform configuration", "Usage and API analytics", "Background job monitoring", "Global notifications"]}
    />
  );
}
