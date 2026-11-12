"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { authService } from "@/services/auth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/errors";

export function VerifyEmail() {
  const token = useSearchParams().get("token");
  const [result, setResult] = useState<{ status: "ok" | "error"; message?: string } | null>(null);
  const state: { status: "pending" | "ok" | "error"; message?: string } = !token
    ? { status: "error", message: "Missing verification token." }
    : (result ?? { status: "pending" });

  useEffect(() => {
    if (!token) return;
    authService
      .confirmEmailVerification(token)
      .then(() => setResult({ status: "ok" }))
      .catch((error) => setResult({ status: "error", message: errorMessage(error) }));
  }, [token]);

  return (
    <Card className="w-full max-w-md text-center">
      <CardHeader>
        <CardTitle>{state.status === "pending" ? "Verifying…" : state.status === "ok" ? "Email verified" : "Verification failed"}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {state.message ? <p className="text-sm text-muted-foreground">{state.message}</p> : null}
        <Button asChild><Link href="/login">Continue to sign in</Link></Button>
      </CardContent>
    </Card>
  );
}
