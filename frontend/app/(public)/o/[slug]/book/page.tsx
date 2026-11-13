import { Suspense } from "react";
import { BookingWizard } from "./wizard";

export default function BookPage() {
  return (
    <Suspense>
      <BookingWizard />
    </Suspense>
  );
}
