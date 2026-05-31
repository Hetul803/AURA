import { AppShell, Badge, Card, PageHeader } from "../../components/ui";

export default function AuditPage() {
  return (
    <AppShell>
      <PageHeader eyebrow="Audit" title="Every approval, block, repair, and export." />
      <div className="p-6 md:p-10">
        <Card>
          <div className="space-y-3 text-sm text-muted-foreground">
            <p><Badge>block</Badge> AURA blocked secret_in_diff in PR #42.</p>
            <p><Badge>export</Badge> Cross-agent memory files generated from AURA.md.</p>
            <p><Badge>repair</Badge> Constrained repair prompt copied for Codex.</p>
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
