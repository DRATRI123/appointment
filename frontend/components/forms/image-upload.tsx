"use client";

import { useRef, useState } from "react";
import { ImagePlus, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { catalogService, mediaUrl } from "@/services/catalog";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/errors";

export function ImageUpload({ value, onChange, label = "Image", disabled, shape = "square" }: { value: string | null; onChange: (url: string | null) => void; label?: string; disabled?: boolean; shape?: "square" | "circle" | "wide" }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const src = mediaUrl(value);
  const size = shape === "wide" ? "h-24 w-40" : "size-24";
  return (
    <div className="flex items-center gap-4">
      <div className={`grid ${size} shrink-0 place-items-center overflow-hidden border bg-muted ${shape === "circle" ? "rounded-full" : "rounded-lg"}`}>
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt="" className="h-full w-full object-cover" />
        ) : (
          <ImagePlus className="size-6 text-muted-foreground" />
        )}
      </div>
      <div className="space-y-2">
        <p className="text-sm font-medium">{label}</p>
        <div className="flex gap-2">
          <Button type="button" size="sm" variant="outline" disabled={disabled || busy} onClick={() => input.current?.click()}>
            {busy ? <Loader2 className="animate-spin" /> : null} Upload
          </Button>
          {value ? <Button type="button" size="sm" variant="ghost" disabled={disabled} onClick={() => onChange(null)}><X /> Remove</Button> : null}
        </div>
        <p className="text-xs text-muted-foreground">PNG, JPEG or WebP up to 5 MB.</p>
        <input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (!file) return;
            setBusy(true);
            try {
              const res = await catalogService.uploadImage(file);
              onChange(res.url);
            } catch (error) {
              toast.error(errorMessage(error));
            } finally {
              setBusy(false);
            }
          }}
        />
      </div>
    </div>
  );
}
