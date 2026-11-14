"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { customersService } from "@/services/customers";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/errors";

/** Owner/admin action for a customer's data-erasure request. The backend decides what is erased and enforces permissions. */
export function EraseCustomerDialog({ customerId, name }: { customerId: string; name: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [understood, setUnderstood] = useState(false);
  const erase = useMutation({
    mutationFn: () => customersService.anonymize(customerId, reason.trim()),
    onSuccess: () => {
      toast.success("Personal data erased");
      setOpen(false);
      queryClient.removeQueries({ queryKey: ["customer", customerId] });
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      router.replace("/admin/customers");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setReason(""); setUnderstood(false); } }}>
      <DialogTrigger asChild><Button size="sm" variant="outline" className="text-destructive-ink">Erase personal data</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Erase {name}&apos;s personal data?</DialogTitle>
          <DialogDescription>Use this when the customer asks for their data to be deleted. It cannot be undone.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div>
            <p className="font-medium">Removed</p>
            <p className="text-muted-foreground">Name, mobile, email, date of birth, address, family members, clinical notes, uploaded documents, booking-form answers, appointment notes, message history and the link to their login.</p>
          </div>
          <div>
            <p className="font-medium">Kept without personal details</p>
            <p className="text-muted-foreground">Appointment dates and services, payments, UTRs, verification logs and refunds, so your accounts still add up.</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="erase-reason">Reason</Label>
            <Textarea id="erase-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Written request received at reception on 14 Nov" rows={2} />
          </div>
          <div className="flex items-start gap-2">
            <Checkbox id="erase-confirm" checked={understood} onCheckedChange={(v) => setUnderstood(v === true)} />
            <Label htmlFor="erase-confirm" className="font-normal leading-snug">I understand this permanently erases the data above.</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>Keep data</Button>
          <Button variant="destructive" disabled={!understood || reason.trim().length < 5 || erase.isPending} onClick={() => erase.mutate()}>{erase.isPending ? "Erasing…" : "Erase data"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
