"use client";

import { safeNextPath } from "@/lib/safe-redirect";
import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "@/lib/zod-config";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { authService } from "@/services/auth";
import { usersService } from "@/services/users";
import { ME_QUERY_KEY, defaultDestination } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Field } from "@/components/forms/field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { errorMessage } from "@/lib/errors";
import { ApiError } from "@/lib/api-client";
import { GoogleSignIn } from "@/components/auth/google-sign-in";

const otpRequestSchema = z.object({ identifier: z.string().min(3, "Enter your mobile number or email") });
const otpVerifySchema = z.object({ code: z.string().regex(/^\d{4,8}$/, "Enter the code you received"), full_name: z.string().optional() });
const passwordSchema = z.object({ email: z.string().email("Enter a valid email"), password: z.string().min(1, "Enter your password") });

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const next = params.get("next");

  const [mfaToken, setMfaToken] = useState<string | null>(null);

  async function finishLogin() {
    const me = await usersService.me();
    queryClient.setQueryData(ME_QUERY_KEY, me);
    router.replace(safeNextPath(next) ?? defaultDestination(me));
  }

  /** Password, mobile code or Google was right; accounts with two-step sign-in need the authenticator code next. */
  function needsSecondStep(error: unknown): boolean {
    if (error instanceof ApiError && error.code === "mfa_required" && error.body?.mfa_token) {
      setMfaToken(error.body.mfa_token);
      return true;
    }
    return false;
  }

  if (mfaToken) {
    return (
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-xl">Two-step sign-in</CardTitle>
          <CardDescription>Open your authenticator app and enter the 6-digit code for this account.</CardDescription>
        </CardHeader>
        <CardContent>
          <MfaStep token={mfaToken} onSuccess={finishLogin} onRestart={() => setMfaToken(null)} />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle className="text-xl">Sign in</CardTitle>
        <CardDescription>Use your mobile number for a one-time code, or your email and password.</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="otp">
          <TabsList className="mb-4 w-full">
            <TabsTrigger value="otp" className="flex-1">Mobile / OTP</TabsTrigger>
            <TabsTrigger value="password" className="flex-1">Email &amp; password</TabsTrigger>
          </TabsList>
          <TabsContent value="otp">
            <OtpLogin onSuccess={finishLogin} onSecondStep={needsSecondStep} />
          </TabsContent>
          <TabsContent value="password">
            <PasswordLogin onSuccess={finishLogin} onSecondStep={needsSecondStep} />
          </TabsContent>
        </Tabs>
        <div className="mt-4"><GoogleSignIn onSuccess={finishLogin} onSecondStep={needsSecondStep} /></div>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          New organization?{" "}
          <Link href="/register" className="font-medium text-primary hover:underline">
            Create an account
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}

function OtpLogin({ onSuccess, onSecondStep }: { onSuccess: () => Promise<void>; onSecondStep: (error: unknown) => boolean }) {
  const [stage, setStage] = useState<"request" | "verify">("request");
  const [identifier, setIdentifier] = useState("");
  const [debugCode, setDebugCode] = useState<string | null>(null);
  const [resendIn, setResendIn] = useState(0);
  const [busy, setBusy] = useState(false);

  const requestForm = useForm<z.infer<typeof otpRequestSchema>>({ resolver: zodResolver(otpRequestSchema), defaultValues: { identifier: "" } });
  const verifyForm = useForm<z.infer<typeof otpVerifySchema>>({ resolver: zodResolver(otpVerifySchema), defaultValues: { code: "", full_name: "" } });

  async function sendCode(values: z.infer<typeof otpRequestSchema>) {
    setBusy(true);
    try {
      const res = await authService.requestOtp(values.identifier);
      setIdentifier(res.identifier);
      setDebugCode(res.debug_code ?? null);
      setResendIn(res.resend_in);
      setStage("verify");
      const timer = setInterval(() => setResendIn((s) => (s <= 1 ? (clearInterval(timer), 0) : s - 1)), 1000);
      toast.success(`Code sent via ${res.channel.toUpperCase()}`);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function verify(values: z.infer<typeof otpVerifySchema>) {
    setBusy(true);
    try {
      await authService.verifyOtp({ identifier, code: values.code, full_name: values.full_name || undefined });
      await onSuccess();
    } catch (error) {
      if (!onSecondStep(error)) toast.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  if (stage === "request") {
    return (
      <form onSubmit={requestForm.handleSubmit(sendCode)} className="space-y-4" data-testid="otp-request-form">
        <Field label="Mobile number or email" htmlFor="identifier" error={requestForm.formState.errors.identifier?.message}>
          <Input id="identifier" inputMode="tel" placeholder="98765 43210" autoComplete="tel" {...requestForm.register("identifier")} />
        </Field>
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? <Loader2 className="animate-spin" /> : null} Send code
        </Button>
      </form>
    );
  }

  return (
    <form onSubmit={verifyForm.handleSubmit(verify)} className="space-y-4" data-testid="otp-verify-form">
      <p className="text-sm text-muted-foreground">
        Code sent to <span className="font-medium text-foreground">{identifier}</span>.{" "}
        <button type="button" className="text-primary hover:underline" onClick={() => setStage("request")}>
          Change
        </button>
      </p>
      {debugCode ? (
        <Alert variant="info" data-testid="debug-code">
          <AlertDescription>
            Development mode: your code is <strong className="font-mono">{debugCode}</strong>
          </AlertDescription>
        </Alert>
      ) : null}
      <Field label="One-time code" htmlFor="code" error={verifyForm.formState.errors.code?.message}>
        <Input id="code" inputMode="numeric" autoComplete="one-time-code" placeholder="123456" className="text-center font-mono text-lg tracking-[0.4em]" {...verifyForm.register("code")} />
      </Field>
      <Field label="Your name (first sign-in only)" htmlFor="full_name" hint="Optional. Used on your bookings.">
        <Input id="full_name" placeholder="Asha Patel" {...verifyForm.register("full_name")} />
      </Field>
      <Button type="submit" className="w-full" disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : null} Verify &amp; continue
      </Button>
      <Button type="button" variant="ghost" className="w-full" disabled={resendIn > 0 || busy} onClick={() => sendCode({ identifier })}>
        {resendIn > 0 ? `Resend in ${resendIn}s` : "Resend code"}
      </Button>
    </form>
  );
}

function PasswordLogin({ onSuccess, onSecondStep }: { onSuccess: () => Promise<void>; onSecondStep: (error: unknown) => boolean }) {
  const form = useForm<z.infer<typeof passwordSchema>>({ resolver: zodResolver(passwordSchema), defaultValues: { email: "", password: "" } });
  const [busy, setBusy] = useState(false);

  async function submit(values: z.infer<typeof passwordSchema>) {
    setBusy(true);
    try {
      await authService.login(values);
      await onSuccess();
    } catch (error) {
      if (!onSecondStep(error)) toast.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={form.handleSubmit(submit)} className="space-y-4" data-testid="password-login-form">
      <Field label="Email" htmlFor="email" error={form.formState.errors.email?.message}>
        <Input id="email" type="email" autoComplete="email" placeholder="you@clinic.com" {...form.register("email")} />
      </Field>
      <Field label="Password" htmlFor="password" error={form.formState.errors.password?.message}>
        <Input id="password" type="password" autoComplete="current-password" {...form.register("password")} />
      </Field>
      <div className="flex items-center justify-between text-sm">
        <Link href="/forgot-password" className="text-primary hover:underline">Forgot password?</Link>
      </div>
      <Button type="submit" className="w-full" disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : null} Sign in
      </Button>
    </form>
  );
}

function MfaStep({ token, onSuccess, onRestart }: { token: string; onSuccess: () => Promise<void>; onRestart: () => void }) {
  const [code, setCode] = useState("");
  const [useBackup, setUseBackup] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await authService.mfaVerify(token, code.trim());
      await onSuccess();
    } catch (err) {
      if (err instanceof ApiError && (err.code === "mfa_token_expired" || err.code === "mfa_token_invalid")) {
        toast.error(err.message);
        onRestart();
        return;
      }
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" data-testid="mfa-form">
      <Field label={useBackup ? "Backup code" : "Authenticator code"} htmlFor="mfa_code" error={error ?? undefined}>
        <Input id="mfa_code" value={code} onChange={(e) => setCode(e.target.value)} autoFocus autoComplete="one-time-code"
          inputMode={useBackup ? "text" : "numeric"} placeholder={useBackup ? "7KQ4-M2XD" : "123456"} maxLength={useBackup ? 12 : 6}
          className="text-center font-mono text-lg tracking-[0.3em]" />
      </Field>
      <Button type="submit" className="w-full" disabled={busy || code.trim().length < 6}>
        {busy ? <Loader2 className="animate-spin" /> : null} Verify &amp; sign in
      </Button>
      <div className="flex justify-between text-sm">
        <button type="button" className="text-primary hover:underline" onClick={() => { setUseBackup((b) => !b); setCode(""); setError(null); }}>
          {useBackup ? "Use the authenticator app" : "Use a backup code"}
        </button>
        <button type="button" className="text-muted-foreground hover:underline" onClick={onRestart}>Start again</button>
      </div>
    </form>
  );
}
