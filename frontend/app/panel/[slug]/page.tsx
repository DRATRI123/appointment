import { Suspense } from "react";
import { PanelSignIn } from "./panel-sign-in";

export const metadata = { title: "Admin panel" };

export default function PanelPage() {
  return (
    <Suspense>
      <PanelSignIn />
    </Suspense>
  );
}
