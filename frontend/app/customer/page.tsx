import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata = { title: "Customer dashboard" };

export default function Page() {
  return (
    <PhasePlaceholder
      title="Customer dashboard"
      description="Upcoming and past appointments, payment history, saved professionals and family profiles."
      phase={5}
      items={["Upcoming appointments", "Appointment history", "Payment receipts", "Family member profiles", "Saved professionals and branches", "Profile and communication preferences"]}
    />
  );
}
