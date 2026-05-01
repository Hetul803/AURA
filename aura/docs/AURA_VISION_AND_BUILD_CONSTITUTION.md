# AURA Vision and Build Constitution

This document is the source of truth for AURA. Every future task, feature, refactor, roadmap update, and implementation decision should read and follow this constitution before changing the product.

AURA is not a small assistant. AURA is the user's private, personal AI operating layer: the layer between the user and their computer, their tools, their agents, their work, and eventually their devices and environments.

Desktop is the first surface. It is not the final scope.

## 1. Core Identity

AURA should feel like a practical, local-first, user-owned JARVIS:

- It sees what the user is doing.
- It understands context.
- It listens when the user talks or types.
- It acts on the user's computer.
- It chooses the right AI model, tool, or agent.
- It protects the user from unsafe actions.
- It remembers the user.
- It works across personal, work, and company contexts.
- It reduces wasted AI cost.
- It creates workspaces and builds apps.
- It handles workflows.
- It eventually follows the user across desktop, phone, car, home, wearable, and enterprise environments.

AURA starts on desktop because desktop gives the richest operating context: active app, active browser tab, selected text, clipboard, files, terminal, IDE, email, documents, and local projects. The architecture must still be designed as a cross-device AI operating layer from the beginning.

Users should not have to think:

- Which app should I open?
- Which folder is this in?
- Which command should I run?
- Should I use ChatGPT, Claude, Codex, a local model, or another tool?
- How much will this cost?
- Where should this project live?
- How do I automate this?

The user should say what they want. AURA should figure out the rest.

Users can rename their personal AURA. Their AURA is theirs. It should feel owned, private, customizable, and personal.

## 2. What AURA Is

AURA is:

- A personal AI OS layer.
- A local-first private assistant.
- An agent orchestrator.
- A computer controller.
- A context-aware workflow layer.
- A memory system.
- A safety and policy layer.
- A cost optimizer.
- A cross-device companion.
- A future enterprise and team AI layer.

AURA is not:

- Only a chatbot.
- Only a voice controller.
- Only a coding assistant.
- Only a browser automation tool.
- Only an email assistant.
- Only a wrapper around Codex, OpenAI, Claude, or Ollama.

AURA should not replace Codex, ChatGPT, Claude, local models, browser automation, email tools, or company systems. AURA should orchestrate them.

Codex is a powerful coding worker. AURA is the system that knows when to use Codex, what to ask it, how to verify the result, how to connect it to files, browser, terminal, email, and GitHub, and how to protect the user while doing it.

## 3. Examples of Magic

### GitHub Context

The user is looking at a GitHub repository in the browser and says:

```text
Hey AURA, clone this repo locally.
```

The user does not provide the URL.

AURA should:

- Detect the current browser tab.
- Understand it is GitHub.
- Extract the repository URL.
- Choose or create an appropriate local workspace folder.
- Ask for confirmation if needed.
- Open or use terminal safely.
- Run `git clone`.
- Verify the clone succeeded.
- Tell the user where it cloned the repository.

### Email Context

The user is looking at an email.

AURA should understand the current email context. The overlay can show:

```text
Reply ready
```

When the user clicks paste, AURA should:

- Draft in the user's tone.
- Ask for approval.
- Paste into Gmail or the active email client.
- Never send without explicit permission.

### Coding and App Creation

The user says:

```text
Create a full app for this idea.
```

AURA should:

- Clarify only if needed.
- Create a project workspace.
- Generate a product spec.
- Decide whether to use Codex, local tools, GPT, Claude, or another agent.
- Set up frontend and backend when needed.
- Create login/auth if needed.
- Connect Supabase if the user approves.
- Connect Redis, Postgres, or other services if needed and approved.
- Create environment templates.
- Run tests.
- Start a local server.
- Inspect the browser.
- Fix errors using Codex or local tools.
- Summarize what was built.
- Optionally commit and push after approval.

### Work and Personal Boundaries

If the user has a personal AURA and a company or work AURA:

- Personal memories must stay separate from company memories.
- Company data must not leak into personal memory.
- Personal data must not leak into company memory.
- AURA must understand context boundaries.
- AURA may coordinate across boundaries only when policy and user permission allow it.

For example, personal AURA can say:

```text
You have a work meeting at 2 PM.
```

or:

```text
You were assigned this coding task. Do you want me to start setting up the workspace?
```

But personal AURA must not copy confidential work data into personal memory unless policy explicitly allows it.

### Cheaper and Better AI Usage

AURA should always consider:

- Can this be handled by a local model?
- Can this be handled by a cheaper model?
- Does this need Codex?
- Does this need Claude, GPT, or another cloud model?
- Can context be compressed?
- Can prior work be cached?
- Can token use be reduced?
- What is the cheapest reliable way to complete the task?

The user should use AURA, and AURA should manage the best AI models, agents, and tools underneath. AURA must not be locked to one model provider.

## 4. Supported Workers and Systems

AURA should be able to use:

- Codex.
- ChatGPT.
- Claude.
- Ollama and other local models.
- Browser automation.
- Terminal and shell.
- Filesystem.
- IDEs.
- Gmail.
- Calendar.
- Documents and PDFs.
- Supabase.
- Redis.
- Postgres.
- GitHub.
- Slack and Teams later.
- Company tools later.
- Phone, home, car, wearable, and enterprise adapters later.

AURA is the orchestrator above all of them.

## 5. Build Philosophy

Do not build random features.

Every feature must strengthen one or more permanent platform primitives:

1. Context Engine.
2. Intent Engine.
3. Agent Router.
4. Tool Registry.
5. Safety/Policy Engine.
6. Memory Engine.
7. Cost Router.
8. Workflow Engine.
9. Identity/Boundary Manager.
10. Device Adapter Layer.
11. Run/Event Timeline.
12. Approval System.
13. Audit Log.

When choosing between a quick demo and a durable primitive, prefer the durable primitive unless the user explicitly asks for a throwaway experiment.

When implementing a task:

- Keep the change scoped to the approved task.
- Preserve the long-term architecture.
- Avoid coupling product logic to a single model provider.
- Avoid coupling platform logic to desktop-only assumptions.
- Prefer typed schemas, explicit permissions, and auditable state.
- Prefer local-first defaults.
- Prefer user approval for risky actions.
- Do not hide important actions from the user.

## 6. Core Platform Primitives

### 6.1 Context Engine

AURA must know what the user is looking at when possible.

The Context Engine should collect and normalize:

- Active app.
- Active window.
- Active browser URL.
- Browser page title.
- Selected text.
- Clipboard.
- Current folder.
- Current repository.
- Current email.
- Current document.
- Current website.
- Current project/workspace.
- User identity and preferences.
- Task history.
- Device state.
- Screen context later through screenshot/OCR when needed and permitted.

Context must be permissioned and privacy-aware. AURA should not silently ingest sensitive context into durable memory without policy and user consent.

### 6.2 Intent Engine

AURA must turn vague commands into executable tasks.

Examples:

- "clone this"
- "reply to this"
- "fix this"
- "build this"
- "continue"
- "summarize that"
- "send this"
- "make it a PDF"
- "find the spreadsheet from last week"
- "start the dev server"

The Intent Engine should combine user command, current context, memory, policy, and available tools to produce a typed task. It should clarify only when needed.

### 6.3 Agent Router

AURA must choose the right worker for each task.

Examples:

- Codex for coding and repo work.
- Browser agent for websites.
- Email agent for Gmail and mail workflows.
- Local shell/filesystem for local tasks.
- LLMs for reasoning, writing, summarization, extraction, and planning.
- Document/PDF agents for office workflows.
- Future phone, home, car, wearable, and company agents.

The Agent Router should decide based on capability, safety, context, cost, latency, privacy, and reliability.

### 6.4 Tool Registry

Every tool must have:

- Name.
- Description.
- Input schema.
- Output/observation schema.
- Permissions.
- Risk level.
- Required approvals.
- Side effects.
- Rollback or undo behavior when possible.
- Audit log requirements.
- Device/environment compatibility.

Tools should not be anonymous function calls hidden inside the executor. They should be registered capabilities that the planner, router, safety engine, UI, and audit log can reason about.

### 6.5 Safety/Policy Engine

AURA must protect the user.

Hard rules:

- Never send email without approval.
- Never delete files without approval.
- Never spend money without approval.
- Never push code without approval.
- Never expose secrets or API keys.
- Never run destructive shell commands without approval.
- Always log important actions.
- Panic stop must work.
- Risky actions must be paused, inspectable, approvable, rejectable, and resumable.

The Safety/Policy Engine should classify actions by risk, apply user policy, apply enterprise policy when relevant, redact secrets, and require explicit approvals for sensitive actions.

### 6.6 Memory Engine

AURA should remember:

- User preferences.
- Writing style.
- Coding style.
- Common folders and projects.
- Preferred commands.
- Workflows.
- People and context if permitted.
- Repeated tasks.
- Previous failures and fixes.
- Safety preferences.
- Model/tool preferences.

Memory must be:

- Local-first.
- Editable.
- Searchable.
- Permissioned.
- Exportable.
- Eventually syncable.
- Provenance-aware.
- Separated by identity and boundary.

AURA should not blindly remember everything. Memory should be useful, explainable, and controllable.

### 6.7 Cost Router

AURA should:

- Track model and tool cost.
- Estimate cost before expensive tasks.
- Route to cheaper or local models when possible.
- Use expensive models only when justified.
- Compress context.
- Cache repeated work.
- Explain savings.
- Respect user budgets.

AURA should make AI usage feel simpler and cheaper for the user.

### 6.8 Workflow Engine

AURA should create reusable workflows.

Examples:

- "Every morning summarize inbox."
- "When I open this project, start the dev server."
- "When professor emails, draft a reply."
- "When a new GitHub issue is assigned, create a workspace."
- "After a Codex task finishes, run tests and summarize changes."

Workflows must support parameters, triggers, schedules, approvals, memory, pause/resume, audit logs, and rollback where possible.

### 6.9 Identity/Boundary Manager

AURA must support:

- Personal identity.
- Work identity.
- Company identity.
- Separate memory stores.
- Explicit context boundaries.
- Permissioned sharing.
- Enterprise policy.
- User-controlled switching.

Personal AURA and company AURA must remain separate unless explicit permission and policy allow coordination.

### 6.10 Device Adapter Layer

Desktop is first. The architecture must later support:

- Phone companion.
- Home assistant.
- Car assistant.
- Wearable or ambient assistant.
- Enterprise and team deployments.

Each device adapter should expose context sources, tools, input methods, output methods, approvals, and policy constraints through common interfaces.

### 6.11 Run/Event Timeline

AURA must keep a durable timeline of:

- User request.
- Context snapshot used.
- Intent interpretation.
- Plan.
- Tool and agent calls.
- Observations.
- Approvals.
- Errors.
- Repairs.
- Final result.
- Memory updates.
- Cost estimates and actuals.

The timeline is essential for trust, debugging, learning, enterprise audit, and cross-device handoff.

### 6.12 Approval System

Approvals must be first-class.

An approval should include:

- Requested action.
- Risk reason.
- Context.
- Proposed inputs.
- Expected side effects.
- Approve, reject, edit, or resume controls.
- Time and identity of approver.
- Audit record.

Approvals must work across desktop first and later phone, wearable, car, and enterprise surfaces.

### 6.13 Audit Log

AURA must maintain an audit log for important actions. For personal AURA, this builds trust and supports debugging. For company AURA, this becomes required for compliance, admin policy, and incident review.

## 7. Future Product Surfaces

### AURA Phone

AURA Phone should support:

- Mobile voice and text.
- Notifications.
- Quick approvals.
- Phone-to-desktop handoff.
- Desktop-to-phone handoff.
- Mobile memory access.
- Camera/share-sheet context where permitted.
- On-the-go assistant workflows.

### AURA Home

AURA Home could support:

- Smart home control.
- Household routines.
- Family reminders.
- Household context if permitted.
- User-specific memory boundaries inside a household.

### AURA Car

AURA Car should be:

- Voice-first.
- Safety-first.
- Navigation-aware.
- Calendar-aware.
- Message-aware with approval.
- Limited to actions appropriate while driving.
- Able to hand tasks to phone or desktop.

### Wearable and Ambient AURA

A wearable or ambient AURA surface could support:

- Fast capture.
- Reminders.
- Notifications.
- Quick approvals.
- Lightweight status updates.

These surfaces should use the same identity, context, memory, safety, run timeline, and workflow primitives.

## 8. Enterprise and Team AURA

AURA starts individual-first, but companies may deploy their own AURA.

A company may have:

- Company AURA.
- Team AURA.
- Department AURA.
- Internal workflow agents.
- Company memory.
- Role-based access control.
- Audit logs.
- Compliance policy.
- Admin controls.
- Company-branded or renamed AURA.

If a user has both personal AURA and company AURA:

- Personal AURA and company AURA remain separate.
- Personal memory does not leak into company context.
- Company secrets do not leak into personal memory.
- Context boundaries are explicit.
- Sharing is permissioned.
- Enterprise policy can restrict actions.
- The user can say "use my work AURA" or "this is personal."

Long term, AURAs can collaborate with permission:

- Meeting scheduling.
- Shared project workflows.
- Team memory.
- Delegated tasks.
- Handoffs.
- Approvals.
- Audit trails.

Privacy boundaries are non-negotiable.

## 9. Product Standard

AURA should feel smart and context-aware, not disconnected.

For any user request, ask:

- What context is the user probably referring to?
- What can AURA infer safely?
- What needs approval?
- What tool or agent is best?
- What is the cheapest reliable path?
- What should be remembered?
- What should never be remembered?
- What should be logged?
- What boundary does this context belong to?

Do not reduce AURA to one use case. AURA must work across professions:

- Students.
- Developers.
- Founders.
- Researchers.
- Analysts.
- Recruiters.
- Lawyers.
- Doctors and administrative staff.
- Sales and business operations.
- Finance and quant users.
- Creators.

AURA is a platform.

## 10. Development Workflow

After each approved task:

1. Inspect the current repo state.
2. Implement only the approved task.
3. Run relevant tests.
4. Update docs if needed.
5. Create a clean commit.
6. Push to GitHub.
7. Summarize:
   - What changed.
   - Files changed.
   - Tests run.
   - Risks.
   - Next recommended task.

Do not start the next task automatically. Wait for the user to say continue.

The user may work from different computers. The repo must stay consistent through GitHub. Commit and push completed tasks unless the user explicitly says not to.

## 11. First Engineering Priority

The first implementation priority should be the durable run, approval, safety, and audit core.

Why:

- Context awareness needs a trustworthy execution record.
- Codex delegation needs approval and audit.
- Email workflows need approval and no-send guarantees.
- Terminal/file operations need safety policy.
- Enterprise AURA needs audit and boundaries.
- Phone and wearable approval surfaces need a common approval model.

Before broad feature expansion, AURA needs one reliable foundation:

- Durable runs.
- Durable events.
- Approval records.
- Policy decisions.
- Audit log.
- Panic stop.
- Pause/resume/reject.
- Risk classification.

Every later system should build on that foundation.

