import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata = { title: "Professional dashboard" };

export default function Page() {
  return (
    <PhasePlaceholder
      title="Professional dashboard"
      description="Today's queue, personal calendar across branches, patient notes and leave management."
      phase={4}
      items={["Today's appointments and check-ins", "Day / week / month calendar", "Per-branch schedules and breaks", "Leave requests", "Clinical notes and documents", "Video consultation links"]}
    />
  );
}
