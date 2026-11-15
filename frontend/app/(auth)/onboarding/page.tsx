"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "@/lib/zod-config";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { RequireAuth } from "@/components/auth/require-auth";
import { useAuth } from "@/components/auth/auth-provider";
import { organizationsService } from "@/services/organizations";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";

const BUSINESS_TYPES = [
  ["clinic", "Doctor / clinic"],
  ["hospital", "Hospital"],
  ["ayurvedic", "Ayurvedic clinic"],
  ["dermatology", "Dermatology clinic"],
  ["wellness", "Wellness centre"],
  ["physiotherapy", "Physiotherapy"],
  ["nutrition", "Nutritionist / dietician"],
  ["consulting", "Consultant"],
  ["salon", "Salon / beauty"],
  ["other", "Other"],
] as const;

const schema = z.object({
  name: z.string().min(2, "Enter the organization name"),
  business_type: z.string().min(1),
  phone: z.string().optional(),
  email: z.string().email("Enter a valid email").or(z.literal("")).optional(),
  timezone: z.string().min(1),
  currency: z.string().length(3),
});

export default function OnboardingPage() {
  return (
    <RequireAuth>
      <OnboardingForm />
    </RequireAuth>
  );
}

function OnboardingForm() {
  const router = useRouter();
  const { refresh, setCurrentOrganizationId, user } = useAuth();
  const [busy, setBusy] = useState(false);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", business_type: "clinic", phone: "", email: user?.email ?? "", timezone: "Asia/Kolkata", currency: "INR" },
  });

  async function submit(values: z.infer<typeof schema>) {
    setBusy(true);
    try {
      const org = await organizationsService.create({ ...values, email: values.email || undefined, phone: values.phone || undefined });
      setCurrentOrganizationId(org.id);
      await refresh();
      toast.success(`${org.name} is ready`);
      router.replace("/admin");
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="w-full max-w-lg">
      <CardHeader>
        <CardTitle className="text-xl">Set up your organization</CardTitle>
        <CardDescription>You become the owner. You can add branches, professionals and staff next.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit(submit)} className="grid gap-4 sm:grid-cols-2" data-testid="onboarding-form">
          <Field label="Organization name" htmlFor="name" className="sm:col-span-2" error={form.formState.errors.name?.message}>
            <Input id="name" placeholder="Sunrise Ayurveda Clinic" {...form.register("name")} />
          </Field>
          <Field label="Business type" htmlFor="business_type">
            <NativeSelect id="business_type" {...form.register("business_type")}>
              {BUSINESS_TYPES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Phone" htmlFor="phone">
            <Input id="phone" inputMode="tel" {...form.register("phone")} />
          </Field>
          <Field label="Contact email" htmlFor="org_email" className="sm:col-span-2" error={form.formState.errors.email?.message}>
            <Input id="org_email" type="email" {...form.register("email")} />
          </Field>
          <Field label="Time zone" htmlFor="timezone">
            <Input id="timezone" {...form.register("timezone")} />
          </Field>
          <Field label="Currency" htmlFor="currency">
            <Input id="currency" maxLength={3} {...form.register("currency")} />
          </Field>
          <Button type="submit" className="sm:col-span-2" disabled={busy}>
            {busy ? <Loader2 className="animate-spin" /> : null} Create organization
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
