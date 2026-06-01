import { AppShell, Badge, Card, PageHeader } from "../../components/ui";
import { agentExports } from "../../lib/data";

export default function MemoryExportPage() {
  return (
    <AppShell>
      <PageHeader eyebrow="Cross-agent memory" title="One Constitution, six agent memory files." />
      <div className="grid gap-4 p-6 md:grid-cols-2 md:p-10">
        {agentExports.map((target) => (
          <Card key={target}>
            <Badge>{target}</Badge>
            <p className="mt-3 text-sm text-muted-foreground">Generated idempotently from AEGIS.md so every agent receives the same project rules.</p>
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
