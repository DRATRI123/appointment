"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/errors";
import { privacyService, type PrivacyPolicy } from "@/services/privacy";

/** "Confirm it is you": password, authenticator code, or a one-time code sent to the account's mobile/email. */
export function ReauthForm({ policy, onDone, submitLabel = "Confirm" }: { policy?: PrivacyPolicy; onDone: () => void; submitLabel?: string }) {
  const hasPassword = policy?.has_password ?? true;
  const [mode, setMode] = useState<"password" | "authenticator" | "code">(hasPassword ? "password" : policy?.has_authenticator ? "authenticator" : "code");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await privacyService.reauth(mode === "password" ? { password: value } : mode === "authenticator" ? { code: value } : { otp_code: value });
      setValue("");
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function sendCode() {
    setError(null);
    try {
      const r = await privacyService.sendCode();
      setSent(r.debug_code ? `Code sent (development: ${r.debug_code})` : "Code sent to your mobile number or email.");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const label = mode === "password" ? "Your password" : mode === "authenticator" ? "Code from your authenticator app" : "Code we sent you";
  return (
    <form onSubmit={submit} className="space-y-3" data-testid="reauth-form">
      <div className="space-y-1.5">
        <Label htmlFor="reauth_value">{label}</Label>
        <Input id="reauth_value" type={mode === "password" ? "password" : "text"} inputMode={mode === "password" ? undefined : "numeric"}
          autoComplete={mode === "password" ? "current-password" : "one-time-code"} autoFocus value={value}
          onChange={(e) => setValue(e.target.value)} aria-invalid={!!error} aria-describedby={error ? "reauth_error" : undefined} />
      </div>
      {mode === "code" ? <Button type="button" variant="outline" size="sm" onClick={sendCode}>Send me a code</Button> : null}
      {sent ? <p className="text-sm text-muted-foreground" role="status">{sent}</p> : null}
      {error ? <p id="reauth_error" className="text-sm text-destructive" role="alert">{error}</p> : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" disabled={busy || !value} data-testid="reauth-submit">{busy ? "Checking…" : submitLabel}</Button>
        {hasPassword && mode !== "password" ? <Button type="button" variant="ghost" size="sm" onClick={() => setMode("password")}>Use password</Button> : null}
        {policy?.has_authenticator && mode !== "authenticator" ? <Button type="button" variant="ghost" size="sm" onClick={() => setMode("authenticator")}>Use authenticator app</Button> : null}
        {mode !== "code" ? <Button type="button" variant="ghost" size="sm" onClick={() => setMode("code")}>Send me a code instead</Button> : null}
      </div>
    </form>
  );
}
