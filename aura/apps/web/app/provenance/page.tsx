import { AppShell, Badge, Card, PageHeader } from "../../components/ui";

export default function ProvenancePage() {
  return (
    <AppShell>
      <PageHeader eyebrow="Provenance" title="Agent → prompt → diff → decision." />
      <div className="p-6 md:p-10">
        <Card>
          <Badge tone="good">Immutable trail</Badge>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">Aegisure captures commit trailers and git notes now; GitHub PR provenance lands through webhooks next.</p>
        </Card>
      </div>
    </AppShell>
  );
}
