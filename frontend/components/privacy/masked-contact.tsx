"use client";

import { useMutation } from "@tanstack/react-query";
import { Eye, Mail, Phone } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/errors";
import { privacyService, type RevealedContact } from "@/services/privacy";

/** True when the API sent a hidden value (for example +9198765XXXXX or atr***@example.com). */
export function isMasked(value?: string | null) {
  return !!value && (value.includes("XXXXX") || value.includes("***@"));
}

/**
 * A patient's mobile and email as the API sent them (hidden for staff when the clinic masks contact details), with a
 * "Show" button for roles allowed to see them. Showing is checked and recorded by the API ("confirm it is you" may be
 * asked). Call and email links appear only for the full values.
 */
export function MaskedContact({
  customerId,
  mobile,
  email,
  revealed,
  onRevealed,
}: {
  customerId: string;
  mobile?: string | null;
  email?: string | null;
  revealed?: RevealedContact | null;
  onRevealed?: (contact: RevealedContact) => void;
}) {
  const { hasPermission } = useAuth();
  const shownMobile = revealed ? revealed.mobile : mobile;
  const shownEmail = revealed ? revealed.email : email;
  const hidden = !revealed && (isMasked(mobile) || isMasked(email));
  const reveal = useMutation({
    mutationFn: () => privacyService.reveal(customerId),
    onSuccess: (contact) => onRevealed?.(contact),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1" data-testid="masked-contact">
      {shownMobile ? (
        <span className="inline-flex items-center gap-1">
          <Phone className="size-3.5" aria-hidden />
          {isMasked(shownMobile) ? <span aria-label="Mobile number, partly hidden">{shownMobile}</span> : <a className="hover:underline" href={`tel:${shownMobile}`}>{shownMobile}</a>}
        </span>
      ) : null}
      {shownEmail ? (
        <span className="inline-flex items-center gap-1">
          <Mail className="size-3.5" aria-hidden />
          {isMasked(shownEmail) ? <span aria-label="Email, partly hidden">{shownEmail}</span> : <a className="hover:underline" href={`mailto:${shownEmail}`}>{shownEmail}</a>}
        </span>
      ) : null}
      {hidden && hasPermission("customers:reveal") ? (
        <Button type="button" size="sm" variant="outline" className="h-7" onClick={() => reveal.mutate()} disabled={reveal.isPending} data-testid="reveal-contact">
          <Eye className="size-3.5" aria-hidden /> {reveal.isPending ? "Showing…" : "Show"}
        </Button>
      ) : null}
    </span>
  );
}
