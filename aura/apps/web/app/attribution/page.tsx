import { AppShell, Badge, Card, PageHeader } from "../../components/ui";

export default function AttributionPage() {
  return (
    <AppShell>
      <PageHeader eyebrow="Attribution" title="Show everything each agent touched." />
      <div className="p-6 md:p-10">
        <Card>
          <div className="grid gap-3 text-sm">
            {["Codex touched auth/session.ts", "Claude Code reviewed billing/checkout.ts", "Human edited README.md"].map((item) => (
              <div key={item} className="flex items-center justify-between border-b border-white/10 py-3 last:border-0">
                <span>{item}</span>
                <Badge>recorded</Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
