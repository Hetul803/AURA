import { AppShell, Badge, Card, PageHeader } from "../../components/ui";

const steps = ["Sign in with GitHub", "Install Aegisure GitHub App", "Pick repositories", "Generate first AEGIS.md", "Enable PR risk checks"];

export default function OnboardingPage() {
  return (
    <AppShell>
      <PageHeader eyebrow="Onboarding" title="Connect one repository and generate its Constitution.">
        Aegisure starts by learning the project rules that every coding agent must follow.
      </PageHeader>
      <div className="grid gap-4 p-6 md:p-10">
        {steps.map((step, index) => (
          <Card key={step} className="flex items-center justify-between">
            <div>
              <Badge>{`Step ${index + 1}`}</Badge>
              <h2 className="mt-2 font-medium">{step}</h2>
            </div>
            <button className="rounded-md border border-white/10 px-3 py-2 text-sm hover:bg-white/[0.06]">Configure</button>
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
