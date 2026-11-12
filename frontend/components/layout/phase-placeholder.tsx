import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function PhasePlaceholder({
  title,
  description,
  phase,
  items,
}: {
  title: string;
  description: string;
  phase: number;
  items: string[];
}) {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
          <p className="mt-1 text-muted-foreground">{description}</p>
        </div>
        <Badge variant="secondary">Delivered in Phase {phase}</Badge>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Planned capabilities</CardTitle>
          <CardDescription>The backend schema for every item below already exists in the Phase 1 migration.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-2 sm:grid-cols-2">
            {items.map((item) => (
              <li key={item} className="flex items-center gap-2 text-sm">
                <span className="size-1.5 rounded-full bg-primary" />
                {item}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
