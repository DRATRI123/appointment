import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata = { title: "Admin overview" };

export default function Page() {
  return (
    <PhasePlaceholder
      title="Overview"
      description="Appointments, collections, pending verifications and performance across branches and professionals."
      phase={10}
      items={["Today's and upcoming appointments", "Verified vs pending collections", "Pending payment verifications", "No-shows and cancellations", "Branch, professional and service performance", "Customer growth", "CSV / Excel export"]}
    />
  );
}
