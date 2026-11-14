"use client";

import { toast } from "sonner";
import { Copy, KeyRound } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Shows a secret exactly once, with a copy button and a clear warning. */
export function SecretReveal({ label, value, onDone }: { label: string; value: string; onDone: () => void }) {
  const copy = async () => { try { await navigator.clipboard.writeText(value); toast.success("Copied"); } catch { toast.error("Copy failed; select the text and copy it."); } };
  return (
    <Alert className="space-y-3" data-testid="secret-reveal">
      <KeyRound />
      <AlertDescription className="space-y-3">
        <p className="font-medium text-foreground">{label}: copy it now. You will not be able to see it again.</p>
        <div className="flex gap-2"><Input readOnly value={value} className="font-mono text-xs" onFocus={(e) => e.target.select()} aria-label={label} data-testid="secret-value" /><Button type="button" size="icon" variant="outline" aria-label="Copy" onClick={copy}><Copy /></Button></div>
        <Button size="sm" variant="ghost" onClick={onDone}>I have stored it safely</Button>
      </AlertDescription>
    </Alert>
  );
}
