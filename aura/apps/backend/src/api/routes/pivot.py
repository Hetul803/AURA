from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from api.security import AuthContext, require_api_auth
from aura.agent_memory_export import build_memory_exports
from aura.attribution import query_attribution_ledger
from aura.constitution import render_constitution, scan_repository
from aura.diff_parser import parse_unified_diff
from aura.diff_risk import analyze_diff
from aura.policy_engine import default_policy_yaml, evaluate_policy
from aura.repair_prompt import generate_repair_prompt
from aura.second_opinion import heuristic_second_opinion
from github.webhooks import WebhookHeaders, WebhookVerificationError, parse_verified_webhook


router = APIRouter()


class DiffAnalyzeRequest(BaseModel):
    diff: str
    repo_path: str | None = None


class RepoPathRequest(BaseModel):
    repo_path: str


class RepairPromptRequest(BaseModel):
    diff: str
    repo_path: str | None = None
    failed_tests: list[str] = []
    agent: str = "codex"


class SecondOpinionRequest(BaseModel):
    diff: str
    author_agent: str = "unknown"


class PolicyEvaluateRequest(BaseModel):
    diff: str
    policy_yaml: str | None = None


@router.post("/diffs/analyze")
async def analyze_diff_endpoint(body: DiffAnalyzeRequest, auth: AuthContext = Depends(require_api_auth)):
    constitution = scan_repository(body.repo_path) if body.repo_path else None
    report = analyze_diff(parse_unified_diff(body.diff), constitution=constitution)
    return {"workspace_id": auth.workspace_id, **report.to_dict()}


@router.post("/repos/constitution/generate")
async def generate_constitution_endpoint(body: RepoPathRequest, auth: AuthContext = Depends(require_api_auth)):
    repo = Path(body.repo_path).resolve()
    if not repo.exists():
        raise HTTPException(status_code=404, detail="Repository path not found")
    constitution = scan_repository(repo)
    return {"workspace_id": auth.workspace_id, "constitution": constitution.to_dict(), "markdown": render_constitution(constitution)}


@router.post("/memory/export")
async def memory_export_endpoint(body: RepoPathRequest, auth: AuthContext = Depends(require_api_auth)):
    constitution = scan_repository(body.repo_path)
    return {"workspace_id": auth.workspace_id, "exports": build_memory_exports(constitution)}


@router.post("/repair-prompts")
async def repair_prompt_endpoint(body: RepairPromptRequest, auth: AuthContext = Depends(require_api_auth)):
    constitution = scan_repository(body.repo_path) if body.repo_path else None
    report = analyze_diff(parse_unified_diff(body.diff), constitution=constitution)
    prompt = generate_repair_prompt(risk_report=report, constitution=constitution, failed_tests=body.failed_tests, agent=body.agent)
    return {"workspace_id": auth.workspace_id, "repair_prompt": prompt.to_dict()}


@router.post("/second-opinion")
async def second_opinion_endpoint(body: SecondOpinionRequest, auth: AuthContext = Depends(require_api_auth)):
    opinion = heuristic_second_opinion(body.diff, author_agent=body.author_agent)
    return {"workspace_id": auth.workspace_id, "second_opinion": opinion.to_dict()}


@router.post("/policies/evaluate")
async def policy_evaluate_endpoint(body: PolicyEvaluateRequest, auth: AuthContext = Depends(require_api_auth)):
    parsed = parse_unified_diff(body.diff)
    report = analyze_diff(parsed)
    evaluation = evaluate_policy(parsed, policy_text=body.policy_yaml or default_policy_yaml(), risk_report=report)
    return {"workspace_id": auth.workspace_id, "risk_report": report.to_dict(), "policy_evaluation": evaluation.to_dict()}


@router.get("/attribution")
async def attribution_endpoint(repo_path: str, agent: str | None = None, auth: AuthContext = Depends(require_api_auth)):
    return {"workspace_id": auth.workspace_id, "records": query_attribution_ledger(repo_path, agent=agent)}


@router.post("/github/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_github_delivery: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
):
    raw = await request.body()
    secret = os.getenv("GITHUB_WEBHOOK_SECRET") or os.getenv("AURA_GITHUB_WEBHOOK_SECRET") or ""
    try:
        event, duplicate = parse_verified_webhook(
            raw,
            WebhookHeaders(event=x_github_event, delivery_id=x_github_delivery, signature_256=x_hub_signature_256),
            secret=secret,
        )
    except WebhookVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    return {"ok": True, "duplicate": duplicate, "event": event.model_dump()}
