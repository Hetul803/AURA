import Link from "next/link";
import { AppShell, Badge, Card, PageHeader } from "../../components/ui";
import { backendGet, type ReposResponse } from "../../lib/api";

export default async function ReposPage() {
  const data = await backendGet<ReposResponse>("/repos", { repos: [] });
  return (
    <AppShell>
      <PageHeader eyebrow="Repositories" title="Connected repos and current agent risk." />
      <div className="grid gap-4 p-6 md:p-10">
        {data.repos.length === 0 ? <Card><p className="text-sm text-muted-foreground">No live repositories connected yet. Connect the GitHub App in onboarding.</p></Card> : data.repos.map((repo) => (
          <Card key={repo.full_name || repo.name} className="flex items-center justify-between">
            <div>
              <Link href="/repos/aegisure/constitution" className="font-medium hover:underline">{repo.full_name || repo.name}</Link>
              <p className="mt-1 text-sm text-muted-foreground">{repo.open_prs || 0} open pull requests</p>
            </div>
            <Badge tone={(repo.risk || 0) > 90 ? "bad" : (repo.risk || 0) > 50 ? "warn" : "good"}>{repo.status || "Connected"} · {repo.risk || 0}</Badge>
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
