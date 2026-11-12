export const metadata = { title: "Privacy" };

export default function Page() {
  return (
    <article className="prose prose-neutral mx-auto max-w-3xl px-4 py-16 dark:prose-invert">
      <h1 className="text-3xl font-semibold tracking-tight">Privacy</h1>
      <p className="mt-4 text-muted-foreground">
        Each organization publishes its own Privacy text from Organization settings (Phase 2). This page renders
        the organization-specific version when a booking page is opened on an organization domain.
      </p>
    </article>
  );
}
