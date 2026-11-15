/**
 * A small, safe Markdown subset for website text: headings (##, ###), paragraphs, bullet and numbered lists,
 * **bold**, *italic*, [links](https://…) and line breaks. It builds React elements directly, so stored text can
 * never inject HTML or script, and links are limited to https, tel, mailto and paths on this site.
 */
import { Fragment, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type Block =
  | { kind: "h2" | "h3" | "p"; text: string }
  | { kind: "ul" | "ol"; items: string[] };

export function parseBlocks(source: string): Block[] {
  const blocks: Block[] = [];
  let para: string[] = [];
  let list: { kind: "ul" | "ol"; items: string[] } | null = null;
  const flush = () => {
    if (para.length) blocks.push({ kind: "p", text: para.join("\n") });
    para = [];
    if (list) blocks.push(list);
    list = null;
  };
  for (const raw of source.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    const bullet = /^\s*[-*•]\s+(.+)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.+)$/.exec(line);
    if (!line.trim()) { flush(); continue; }
    if (heading) { flush(); blocks.push({ kind: heading[1].length === 3 ? "h3" : "h2", text: heading[2] }); continue; }
    if (bullet || numbered) {
      const kind = bullet ? "ul" : "ol";
      if (para.length) { blocks.push({ kind: "p", text: para.join("\n") }); para = []; }
      if (!list || list.kind !== kind) { if (list) blocks.push(list); list = { kind, items: [] }; }
      list.items.push((bullet ?? numbered)![1]);
      continue;
    }
    if (list) { blocks.push(list); list = null; }
    para.push(line);
  }
  flush();
  return blocks;
}

export function safeHref(href: string): string | null {
  const h = href.trim();
  if (/^https:\/\/[^\s"'<>]+$/i.test(h)) return h;
  if (/^(tel:\+?[\d\s()-]{6,20}|mailto:[^\s"'<>@]+@[^\s"'<>]+)$/i.test(h)) return h.replace(/\s/g, "");
  if (/^\/[a-z0-9/_#?=&.-]*$/i.test(h) && !h.startsWith("//") && !h.includes("..")) return h;
  if (/^#[a-z0-9-]+$/i.test(h)) return h;
  return null;
}

const INLINE = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|_[^_\s][^_]*_|\[[^\]]+\]\([^)\s]+\))/g;

export function renderInline(text: string, key = ""): ReactNode[] {
  const out: ReactNode[] = [];
  text.split("\n").forEach((line, li) => {
    if (li > 0) out.push(<br key={`${key}br${li}`} />);
    line.split(INLINE).forEach((part, i) => {
      const k = `${key}-${li}-${i}`;
      if (!part) return;
      if (part.startsWith("**") && part.endsWith("**")) out.push(<strong key={k}>{part.slice(2, -2)}</strong>);
      else if ((part.startsWith("*") && part.endsWith("*")) || (part.startsWith("_") && part.endsWith("_"))) out.push(<em key={k}>{part.slice(1, -1)}</em>);
      else if (part.startsWith("[")) {
        const m = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(part);
        const href = m ? safeHref(m[2]) : null;
        if (m && href) {
          const external = href.startsWith("https://");
          out.push(<a key={k} href={href} className="font-medium underline underline-offset-4 hover:opacity-80" {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}>{m[1]}</a>);
        } else out.push(<Fragment key={k}>{m ? m[1] : part}</Fragment>);
      } else out.push(<Fragment key={k}>{part}</Fragment>);
    });
  });
  return out;
}

export function Markdown({ source, className }: { source: string; className?: string }) {
  return (
    <div className={cn("space-y-4 leading-relaxed", className)}>
      {parseBlocks(source).map((b, i) => {
        if ("items" in b) {
          const items = b.items.map((item, j) => <li key={j}>{renderInline(item, `${i}-${j}`)}</li>);
          return b.kind === "ul"
            ? <ul key={i} className="list-disc space-y-1.5 pl-5">{items}</ul>
            : <ol key={i} className="list-decimal space-y-1.5 pl-5">{items}</ol>;
        }
        if (b.kind === "h2") return <h3 key={i} className="pt-2 text-xl font-semibold tracking-tight">{renderInline(b.text, `${i}`)}</h3>;
        if (b.kind === "h3") return <h4 key={i} className="pt-1 text-lg font-semibold">{renderInline(b.text, `${i}`)}</h4>;
        return <p key={i}>{renderInline(b.text, `${i}`)}</p>;
      })}
    </div>
  );
}
