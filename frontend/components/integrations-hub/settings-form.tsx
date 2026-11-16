"use client";

import { useMemo, useState } from "react";
import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import type { SavePayload, SettingField } from "@/services/platform-integrations";

const SOURCE_LABEL = { panel: "saved here", env: "from .env", default: "default" } as const;

function initialValues(fields: SettingField[]) {
  const out: Record<string, unknown> = {};
  for (const f of fields) if (f.kind !== "secret") out[f.name] = f.value ?? (f.kind === "bool" ? false : "");
  return out;
}

/**
 * A form built from field definitions sent by the API. Secrets are never shown: an empty secret box keeps the stored
 * value. "Use .env value" removes what was saved here, so the server's .env (or the default) applies again.
 */
export function SettingsForm({
  idPrefix,
  fields,
  disabled,
  busy,
  showSource = true,
  onSave,
  submitLabel = "Save",
}: {
  idPrefix: string;
  fields: SettingField[];
  disabled?: boolean;
  busy?: boolean;
  showSource?: boolean;
  onSave: (payload: SavePayload) => void;
  submitLabel?: string;
}) {
  const [values, setValues] = useState<Record<string, unknown>>(() => initialValues(fields));
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [clear, setClear] = useState<string[]>([]);
  const visible = useMemo(() => fields.filter((f) => !f.when || String(values[f.when[0]] ?? "") === f.when[1]), [fields, values]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const changed: Record<string, unknown> = {};
    for (const f of fields) {
      if (f.kind === "secret" || clear.includes(f.name)) continue;
      const before = f.value ?? (f.kind === "bool" ? false : "");
      if (values[f.name] !== before) changed[f.name] = values[f.name];
    }
    onSave({ values: changed, secrets: Object.fromEntries(Object.entries(secrets).filter(([, v]) => v.trim())), clear });
    setSecrets({});
  }

  return (
    <form className="space-y-4" onSubmit={submit} data-testid={`${idPrefix}-form`}>
      <div className="grid gap-4 sm:grid-cols-2">
        {visible.map((f) => {
          const id = `${idPrefix}_${f.name}`;
          const cleared = clear.includes(f.name);
          const helpId = f.help ? `${id}_help` : undefined;
          return (
            <div key={f.name} className={f.kind === "bool" ? "sm:col-span-2" : "space-y-1.5"}>
              {f.kind === "bool" ? (
                <div className="flex items-center justify-between rounded-lg border px-3 py-2">
                  <label htmlFor={id} className="text-sm font-medium">{f.label}</label>
                  <Switch id={id} checked={!!values[f.name]} disabled={disabled} onCheckedChange={(v) => setValues({ ...values, [f.name]: v })} />
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between gap-2">
                    <Label htmlFor={id}>{f.label}{f.required ? <span className="text-destructive" aria-hidden> *</span> : null}</Label>
                    {showSource && f.source ? (
                      <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                        {cleared ? "will use .env" : SOURCE_LABEL[f.source]}
                        {f.source === "panel" && !disabled && !cleared ? (
                          <button type="button" className="inline-flex items-center gap-0.5 text-primary hover:underline" onClick={() => setClear([...clear, f.name])}
                            aria-label={`Use the .env value for ${f.label}`}>
                            <RotateCcw className="size-3" aria-hidden /> use .env
                          </button>
                        ) : null}
                      </span>
                    ) : null}
                  </div>
                  {f.kind === "choice" ? (
                    <NativeSelect id={id} value={String(values[f.name] ?? "")} disabled={disabled || cleared} aria-describedby={helpId}
                      onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}>
                      {f.choices.map((c) => <option key={c} value={c}>{c || "None"}</option>)}
                    </NativeSelect>
                  ) : f.kind === "secret" ? (
                    <Input id={id} type="password" autoComplete="new-password" disabled={disabled || cleared} aria-describedby={helpId}
                      placeholder={f.is_set ? `Saved (${f.hint ?? "set"}). Leave empty to keep` : "Not set"}
                      value={secrets[f.name] ?? ""} onChange={(e) => setSecrets({ ...secrets, [f.name]: e.target.value })} />
                  ) : (
                    <Input id={id} type={f.kind === "number" ? "number" : "text"} step="any" disabled={disabled || cleared} aria-describedby={helpId}
                      value={String(values[f.name] ?? "")} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />
                  )}
                  {f.help ? <p id={helpId} className="text-xs text-muted-foreground">{f.help}</p> : null}
                </>
              )}
            </div>
          );
        })}
      </div>
      {!disabled ? (
        <div className="flex justify-end">
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : submitLabel}</Button>
        </div>
      ) : null}
    </form>
  );
}
