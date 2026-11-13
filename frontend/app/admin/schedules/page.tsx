import { Suspense } from "react";
import { SchedulesPage } from "./schedules";

export default function Page() {
  return (
    <Suspense>
      <SchedulesPage />
    </Suspense>
  );
}
