import { BarChart3, Blocks, Bot, Calendar, Cloud, Code2, FileSpreadsheet, Globe, Mail, MessageSquareText, ShoppingBag, Users, Video, Webhook } from "lucide-react";
import { SocialIcon } from "@/components/website/icons";
import { cn } from "@/lib/utils";

/** A neutral mark per provider (a monogram or icon on a tinted tile). Real brand logos are not bundled. */
const MARKS: Record<string, { text?: string; tint: string }> = {
  gmail: { text: "G", tint: "bg-red-500/10 text-red-700 dark:text-red-300" },
  google_contacts: { text: "G", tint: "bg-blue-500/10 text-blue-700 dark:text-blue-300" },
  google_drive: { text: "G", tint: "bg-amber-500/15 text-amber-800 dark:text-amber-300" },
  google_calendar: { text: "G", tint: "bg-blue-500/10 text-blue-700 dark:text-blue-300" },
  google_meet: { text: "G", tint: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" },
  google_signin: { text: "G", tint: "bg-slate-500/10 text-slate-700 dark:text-slate-300" },
  ga4: { text: "GA", tint: "bg-orange-500/10 text-orange-700 dark:text-orange-300" },
  zoom: { text: "Z", tint: "bg-sky-500/10 text-sky-700 dark:text-sky-300" },
  n8n: { text: "n8n", tint: "bg-rose-500/10 text-rose-700 dark:text-rose-300" },
  hubspot: { text: "HS", tint: "bg-orange-500/10 text-orange-700 dark:text-orange-300" },
  zoho_crm: { text: "Z", tint: "bg-red-500/10 text-red-700 dark:text-red-300" },
  zoho_books: { text: "ZB", tint: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" },
  tally: { text: "T", tint: "bg-indigo-500/10 text-indigo-700 dark:text-indigo-300" },
};

const ICONS: Record<string, React.ElementType> = {
  email: Mail, sms: MessageSquareText, video: Video, automation: Bot, shopify: ShoppingBag, website: Globe, crm: Users, accounting: FileSpreadsheet,
  storage: Cloud, analytics: BarChart3, api: Code2, webhooks: Webhook, google: Calendar,
};

export function ProviderMark({ provider, category, className }: { provider: string; category: string; className?: string }) {
  const mark = MARKS[provider];
  const base = cn("flex size-10 shrink-0 items-center justify-center rounded-lg text-sm font-bold", className);
  if (provider.includes("whatsapp")) return <span className={cn(base, "bg-green-500/10 text-green-700 dark:text-green-300")} aria-hidden><SocialIcon network="whatsapp" className="size-5" /></span>;
  if (mark) return <span className={cn(base, mark.tint)} aria-hidden>{mark.text}</span>;
  const Icon = ICONS[category] ?? Blocks;
  return <span className={cn(base, "bg-muted text-muted-foreground")} aria-hidden><Icon className="size-5" /></span>;
}
