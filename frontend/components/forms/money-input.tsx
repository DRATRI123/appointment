"use client";

import { Input } from "@/components/ui/input";

/** Rupee input bound to an integer-paise value. */
export function MoneyInput({
  id,
  valuePaise,
  onChange,
  disabled,
  placeholder,
  allowEmpty = false,
}: {
  id?: string;
  valuePaise: number | null;
  onChange: (paise: number | null) => void;
  disabled?: boolean;
  placeholder?: string;
  allowEmpty?: boolean;
}) {
  return (
    <div className="relative">
      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">₹</span>
      <Input
        id={id}
        type="number"
        inputMode="decimal"
        min={0}
        step="0.01"
        className="pl-7"
        disabled={disabled}
        placeholder={placeholder}
        value={valuePaise === null ? "" : (valuePaise / 100).toString()}
        onChange={(e) => {
          if (e.target.value === "") {
            onChange(allowEmpty ? null : 0);
            return;
          }
          const rupees = Number(e.target.value);
          onChange(Number.isFinite(rupees) ? Math.round(rupees * 100) : 0);
        }}
      />
    </div>
  );
}
