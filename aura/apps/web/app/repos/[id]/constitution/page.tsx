import { AppShell, Badge, Card, PageHeader } from "../../../../components/ui";

export default function ConstitutionPage() {
  return (
    <AppShell>
      <PageHeader eyebrow="AURA.md" title="Project Constitution editor">
        Edit the canonical rules that become AGENTS.md, CLAUDE.md, Cursor, Cline/Roo, and Copilot memory.
      </PageHeader>
      <div className="grid gap-6 p-6 md:grid-cols-[1fr_340px] md:p-10">
        <Card>
          <textarea className="min-h-[480px] w-full resize-y rounded-md border border-white/10 bg-black p-4 font-mono text-sm leading-6 outline-none" defaultValue={`# AURA Constitution\n\n## Agent Rules\n- Inspect before editing\n- Do not remove tests\n- Ask before protected paths\n`} />
        </Card>
        <Card>
          <Badge tone="good">Versioned</Badge>
          <h2 className="mt-3 font-medium">Constitution health</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">Last generated from repo scan. Next step: save and export cross-agent memory files.</p>
          <button className="mt-4 rounded-md bg-white px-3 py-2 text-sm font-medium text-black">Export all formats</button>
        </Card>
      </div>
    </AppShell>
  );
}
