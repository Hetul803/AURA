import { AppShell, Badge, Card, PageHeader } from "../../components/ui";

export default function PoliciesPage() {
  return (
    <AppShell>
      <PageHeader eyebrow="Policy as code" title="Write rules that every agent must obey." />
      <div className="grid gap-6 p-6 md:grid-cols-[1fr_340px] md:p-10">
        <Card>
          <textarea className="min-h-[420px] w-full rounded-md border border-white/10 bg-black p-4 font-mono text-sm outline-none" defaultValue={`rules:\n  - id: protected_payments\n    paths: ["*payment*", "*billing*", "*stripe*"]\n    decision: require_review\n  - id: secret_or_destructive_change\n    categories: ["secret_in_diff", "destructive_shell_command"]\n    decision: block\n`} />
        </Card>
        <Card>
          <Badge tone="warn">Live evaluation</Badge>
          <p className="mt-3 text-sm text-muted-foreground">Paste a sample diff to see pass, require review, or block before saving.</p>
        </Card>
      </div>
    </AppShell>
  );
}
