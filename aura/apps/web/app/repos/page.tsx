import Link from "next/link";
import { AppShell, Badge, Card, PageHeader } from "../../components/ui";
import { sampleRepos } from "../../lib/data";

export default function ReposPage() {
  return (
    <AppShell>
      <PageHeader eyebrow="Repositories" title="Connected repos and current agent risk." />
      <div className="grid gap-4 p-6 md:p-10">
        {sampleRepos.map((repo) => (
          <Card key={repo.name} className="flex items-center justify-between">
            <div>
              <Link href="/repos/aura/constitution" className="font-medium hover:underline">{repo.name}</Link>
              <p className="mt-1 text-sm text-muted-foreground">{repo.prs} open pull requests</p>
            </div>
            <Badge tone={repo.risk > 90 ? "bad" : repo.risk > 50 ? "warn" : "good"}>{repo.status} · {repo.risk}</Badge>
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
