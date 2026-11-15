"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "@/lib/zod-config";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { authService } from "@/services/auth";
import { usersService } from "@/services/users";
import { ME_QUERY_KEY } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";

const schema = z.object({
  full_name: z.string().min(2, "Enter your name"),
  email: z.string().email("Enter a valid email"),
  mobile: z.string().optional(),
  password: z.string().min(8, "At least 8 characters").regex(/[A-Za-z]/, "Include a letter").regex(/\d/, "Include a number"),
});

export default function RegisterPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { full_name: "", email: "", mobile: "", password: "" } });

  async function submit(values: z.infer<typeof schema>) {
    setBusy(true);
    try {
      await authService.register({ ...values, mobile: values.mobile || undefined });
      queryClient.setQueryData(ME_QUERY_KEY, await usersService.me());
      toast.success("Account created");
      router.replace("/onboarding");
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle className="text-xl">Create your account</CardTitle>
        <CardDescription>Set up the owner account first, then your organization.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit(submit)} className="space-y-4" data-testid="register-form">
          <Field label="Full name" htmlFor="full_name" error={form.formState.errors.full_name?.message}>
            <Input id="full_name" autoComplete="name" {...form.register("full_name")} />
          </Field>
          <Field label="Email" htmlFor="email" error={form.formState.errors.email?.message}>
            <Input id="email" type="email" autoComplete="email" {...form.register("email")} />
          </Field>
          <Field label="Mobile (optional)" htmlFor="mobile" error={form.formState.errors.mobile?.message}>
            <Input id="mobile" inputMode="tel" placeholder="98765 43210" {...form.register("mobile")} />
          </Field>
          <Field label="Password" htmlFor="password" error={form.formState.errors.password?.message} hint="At least 8 characters with letters and numbers.">
            <Input id="password" type="password" autoComplete="new-password" {...form.register("password")} />
          </Field>
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? <Loader2 className="animate-spin" /> : null} Continue
          </Button>
        </form>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Already have an account? <Link href="/login" className="font-medium text-primary hover:underline">Sign in</Link>
        </p>
      </CardContent>
    </Card>
  );
}
