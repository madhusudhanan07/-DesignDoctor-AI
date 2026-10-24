"""Demo UI: chat with your agent and watch each Strands Decider 2B decision as it happens.

    ./kit demo            # http://localhost:8501
    DEMO_TARGET=agentcore AGENTCORE_ARN=arn:... ./kit demo     # talk to the agent deployed on AWS

The page has the conversation on the left and a decision panel on the right (each question's
probability, the verdict, and how long the decider and the whole turn took). It is also what
`./kit video` records.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import boto3
import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles
from pydantic import BaseModel

from decider_kit.config import load_dotenv

load_dotenv()
STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Strands Decider hackathon demo")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_agent: Any = None


class Turn(BaseModel):
    message: str
    session_id: str = "demo"
    images: list[str] = []  # base64 (data: URLs accepted), from the attach button
    url: str | None = None


class AuditPayload(BaseModel):
    url: str
    tool: str = "all"


def agent() -> Any:
    global _agent
    if _agent is None:
        if os.environ.get("DEMO_TARGET") == "agentcore":
            _agent = AgentCoreClient(os.environ["AGENTCORE_ARN"])
        else:
            from agent.agent import HackathonAgent

            _agent = HackathonAgent()
    return _agent


class AgentCoreClient:
    """The same `chat()` interface, served by the agent deployed on Amazon Bedrock AgentCore Runtime."""

    def __init__(self, arn: str):
        import boto3

        self.arn = arn
        self.client = boto3.client("bedrock-agentcore", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        self.sessions: dict[str, str] = {}

    def chat(self, message: str, session_id: str = "demo", images: list[str] | None = None) -> dict[str, Any]:
        sid = self.sessions.setdefault(session_id, f"demo-{session_id}-{uuid.uuid4().hex}")
        payload = {"prompt": message, **({"images": images} if images else {})}
        r = self.client.invoke_agent_runtime(agentRuntimeArn=self.arn, runtimeSessionId=sid,
                                             payload=json.dumps(payload).encode())
        body = r["response"].read() if hasattr(r["response"], "read") else r["response"]
        out = json.loads(body)
        out["served_by"] = "Amazon Bedrock AgentCore Runtime"
        return out


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/app.css")
def get_css() -> FileResponse:
    return FileResponse(STATIC / "app.css", media_type="text/css")


@app.get("/app.js")
def get_js() -> FileResponse:
    return FileResponse(STATIC / "app.js", media_type="application/javascript")


def _check_llm_status() -> dict[str, Any]:
    from decider_kit.config import settings

    s = settings()
    provider = os.environ.get("LLM_PROVIDER", "bedrock").lower()

    if provider == "bedrock":
        try:
            import boto3

            sess = boto3.Session(region_name=s.aws_region)
            creds = sess.get_credentials()
            if not creds or not creds.access_key:
                return {
                    "provider": "bedrock",
                    "model": s.bedrock_model,
                    "region": s.aws_region,
                    "status": "unconfigured",
                    "connected": False,
                    "label": f"Bedrock ({s.bedrock_model}) - Unconfigured",
                    "badge": "Unconfigured (No Keys)",
                    "detail": "AWS credentials not detected. Static website auditing remains 100% functional without LLM.",
                }
            sts = sess.client("sts")
            ident = sts.get_caller_identity()
            acct = ident.get("Account", "unknown")
            msg = f"Authenticated with AWS Account {acct}"
            return {
                "provider": "bedrock",
                "model": s.bedrock_model,
                "region": s.aws_region,
                "status": "connected",
                "connected": True,
                "account": acct,
                "label": f"Bedrock ({s.bedrock_model})",
                "badge": f"Connected (Acct {acct[-4:]})",
                "detail": msg,
                "message": msg,
            }
        except Exception as e:
            err_msg = str(e)
            is_unconfigured = "credentials" in err_msg.lower() or "nocredential" in err_msg.lower()
            status_str = "unconfigured" if is_unconfigured else "unavailable"
            msg = f"AWS credentials not detected: {err_msg[:100]}" if is_unconfigured else f"AWS connection check failed: {err_msg[:100]}"
            return {
                "provider": "bedrock",
                "model": s.bedrock_model,
                "region": s.aws_region,
                "status": status_str,
                "connected": False,
                "label": f"Bedrock ({s.bedrock_model}) - {'Unconfigured' if is_unconfigured else 'Unavailable'}",
                "badge": "Unconfigured (No Keys)" if is_unconfigured else "Unavailable",
                "detail": msg,
                "message": msg,
            }
    elif provider == "ugmdu":
        has_key = bool(s.decider_api_key and s.decider_api_key != "your_ugmdu_key_here")
        msg = "Hosted API key set in .env" if has_key else "Set DECIDER_API_KEY in .env"
        return {
            "provider": "ugmdu",
            "model": os.environ.get("LLM_MODEL_ID", "qwen3.5-4b"),
            "status": "configured" if has_key else "unconfigured",
            "connected": has_key,
            "label": "UGMdu Cloud" if has_key else "UGMdu Cloud (No Key)",
            "badge": "Configured" if has_key else "No Key",
            "detail": msg,
            "message": msg,
        }
    elif provider == "local":
        ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
        try:
            with urllib.request.urlopen(f"{ollama_url}/api/version", timeout=0.5) as r:
                msg = "Connected to local Ollama server"
                return {
                    "provider": "local",
                    "model": os.environ.get("LLM_MODEL_ID", "qwen3.5:4b"),
                    "status": "connected",
                    "connected": True,
                    "label": f"Ollama ({os.environ.get('LLM_MODEL_ID', 'qwen3.5:4b')})",
                    "badge": "Local Connected",
                    "detail": msg,
                    "message": msg,
                }
        except Exception:
            msg = f"No Ollama service running at {ollama_url}"
            return {
                "provider": "local",
                "model": os.environ.get("LLM_MODEL_ID", "qwen3.5:4b"),
                "status": "unavailable",
                "connected": False,
                "label": "Ollama (Offline)",
                "badge": "Offline",
                "detail": msg,
                "message": msg,
            }
    return {
        "provider": provider,
        "status": "unknown",
        "connected": False,
        "label": provider,
        "badge": "Unknown",
        "detail": "",
        "message": "",
    }


def _check_decider_status() -> dict[str, Any]:
    from decider_kit.config import settings

    s = settings()
    mode = s.decider_mode
    if mode == "ugmdu":
        has_key = bool(s.decider_api_key and s.decider_api_key != "your_ugmdu_key_here")
        endpoint_live = False
        try:
            resp = httpx.get(f"{s.decider_url}/v1/models", timeout=1.5)
            endpoint_live = (resp.status_code == 200)
        except Exception:
            endpoint_live = False

        if has_key and endpoint_live:
            msg = f"Connected to hosted API ({s.decider_url})"
            return {
                "mode": "ugmdu",
                "status": "connected",
                "connected": True,
                "label": "Decider: Hosted 2B Active",
                "badge": "Hosted 2B Active",
                "detail": msg,
                "message": msg,
                "fallback": None,
                "target": "ugmdu hosted",
                "endpoint": s.decider_url,
            }
        elif endpoint_live and not has_key:
            msg = f"Hosted endpoint live at {s.decider_url}. DECIDER_API_KEY required in .env for neural routing. Rule-based heuristic fallback active."
            return {
                "mode": "ugmdu",
                "status": "unconfigured",
                "connected": False,
                "label": "Decider: Key Required",
                "badge": "Key Required (Heuristic)",
                "detail": msg,
                "message": msg,
                "fallback": "heuristic_fallback",
                "target": "ugmdu hosted",
                "endpoint": s.decider_url,
            }
        else:
            msg = f"Hosted endpoint at {s.decider_url} is unreachable. Rule-based heuristic fallback active."
            return {
                "mode": "ugmdu",
                "status": "offline",
                "connected": False,
                "label": "Decider: Hosted (Offline)",
                "badge": "Offline (Fallback Active)",
                "detail": msg,
                "message": msg,
                "fallback": "heuristic_fallback",
                "target": "ugmdu hosted",
                "endpoint": s.decider_url,
            }
    elif mode == "local":
        try:
            resp = httpx.get(f"{s.decider_url}/health", timeout=0.5)
            if resp.status_code == 200:
                msg = "Connected to local strands-decider server"
                return {
                    "mode": "local",
                    "status": "connected",
                    "connected": True,
                    "label": "Strands Decider: Local 2B (:8099)",
                    "badge": "Local 2B Live",
                    "detail": msg,
                    "message": msg,
                    "fallback": None,
                }
        except Exception as ex:
            msg = f"Local strands-decider is not running on port 8099 ({str(ex)[:50]}). Automatic transparent heuristic routing active."
            return {
                "mode": "local",
                "status": "offline",
                "connected": False,
                "label": "Decider: Offline (:8099)",
                "badge": "Offline (Fallback Active)",
                "detail": msg,
                "message": msg,
                "fallback": "heuristic_fallback",
            }
    return {
        "mode": mode,
        "status": "unconfigured",
        "connected": False,
        "label": f"Strands Decider: {mode}",
        "badge": "Unconfigured",
        "detail": "Decider mode unconfigured",
        "message": "Decider mode unconfigured",
        "fallback": "heuristic_fallback",
    }



@app.get("/api/info")
def info() -> dict[str, Any]:
    from decider_kit.config import settings

    s = settings()
    name = "DesignDoctor AI"
    try:
        from agent import agent as mod

        name = getattr(mod, "NAME", name)
    except Exception:  # noqa: BLE001
        pass

    llm_info = _check_llm_status()
    dec_info = _check_decider_status()

    # Legacy strings preserved for hackathon kit tools
    legacy_llm = llm_info["label"]
    legacy_decider = s.decider_mode

    return {
        "agent": name,
        "llm": legacy_llm,
        "llm_details": llm_info,
        "bedrock_model": s.bedrock_model,
        "decider": legacy_decider,
        "decider_details": dec_info,
        "static_auditor": {
            "status": "operational",
            "connected": True,
            "label": "Static Audit Engine (100% Operational)",
            "badge": "Operational",
            "tools": ["audit_accessibility", "audit_typography", "audit_layout", "audit_performance_hints"],
        },
        "target": os.environ.get("DEMO_TARGET", "local"),
    }


@app.post("/api/chat")
def chat(t: Turn) -> JSONResponse:
    try:
        a = agent()
        import inspect
        sig = inspect.signature(a.chat).parameters
        kwargs: dict[str, Any] = {}
        if "url" in sig and t.url:
            kwargs["url"] = t.url

        if t.images:
            if "images" not in sig:
                return JSONResponse({"error": "this agent does not take images: add images=None to HackathonAgent.chat"},
                                    status_code=400)
            return JSONResponse(a.chat(t.message, t.session_id, images=t.images, **kwargs))
        return JSONResponse(a.chat(t.message, t.session_id, **kwargs))
    except Exception as e:  # noqa: BLE001
        err_str = str(e)
        err_type = type(e).__name__

        # Never leak raw HTML (CloudFront 504/502 pages) to the browser
        if "<html" in err_str.lower() or "doctype" in err_str.lower():
            if "504" in err_str or "gateway" in err_str.lower():
                msg = "The upstream LLM service returned a 504 Gateway Timeout. It may be overloaded — please try again in a moment."
            elif "502" in err_str:
                msg = "The upstream LLM service returned a 502 Bad Gateway error. Please try again shortly."
            elif "503" in err_str:
                msg = "The upstream LLM service is temporarily unavailable (503). Please try again shortly."
            else:
                msg = "The upstream service returned an unexpected HTML error page. Please try again."
            return JSONResponse({"error": msg, "retryable": True}, status_code=503)

        # Timeout errors
        if "timeout" in err_str.lower() or "timed out" in err_str.lower() or err_type in ("TimeoutError", "ReadTimeout"):
            return JSONResponse({
                "error": "The LLM request timed out. The inference service may be busy — please wait 30 seconds and try again.",
                "retryable": True,
            }, status_code=503)

        # Everything else: sanitise and return as a clean JSON error
        # Remove any HTML tags that might have slipped through
        import re
        clean = re.sub(r"<[^>]+>", "", err_str)[:300]
        return JSONResponse({"error": f"{err_type}: {clean}"}, status_code=500)


@app.post("/api/reset")
def reset() -> dict[str, bool]:
    global _agent
    _agent = None
    return {"ok": True}


def _calculate_audit_score(results: dict[str, Any]) -> dict[str, Any]:
    """Calculate overall health score strictly from measured, tested categories.

    Never treats missing data as 0 or 100. Aggregates only from valid measured results.
    """
    all_pillars = ["accessibility", "typography", "layout", "performance"]
    tested_scores: list[int] = []
    tested_names: list[str] = []
    failed_names: list[str] = []

    for name in all_pillars:
        pillar = results.get(name, {})
        status = pillar.get("status") or pillar.get("state")
        score = pillar.get("score")
        if status in ("tested", "partially_tested") and isinstance(score, (int, float)):
            tested_scores.append(int(score))
            tested_names.append(name.capitalize())
        elif status == "failed":
            failed_names.append(name.capitalize())

    tested_count = len(tested_scores)
    if tested_count == 4 and not failed_names:
        overall_score = round(sum(tested_scores) / 4)
        is_partial = False
        coverage_label = "Full Suite (4/4 Categories Measured — 100% Coverage)"
        coverage_warning = None
    elif tested_count > 0:
        overall_score = round(sum(tested_scores) / tested_count)
        is_partial = True
        coverage_pct = round(tested_count / 4 * 100)
        coverage_label = f"Partial Audit ({tested_count}/4 Categories - {coverage_pct}% Coverage)"
        untested = [p.capitalize() for p in all_pillars if p.capitalize() not in tested_names and p.capitalize() not in failed_names]
        parts = []
        if tested_count == 1:
            parts.append(f"Only {tested_names[0]} was tested. Scores reflect only the audited pillar. Aggregate score does not represent full UX health.")
        else:
            parts.append(f"Score reflects only {tested_count} measured categories ({', '.join(tested_names)}).")
        if failed_names:
            parts.append(f"{', '.join(failed_names)} check failed and was excluded from the aggregate score.")
        if untested:
            parts.append(f"Untested categories ({', '.join(untested)}) are not counted as zero or perfect.")
        coverage_warning = " ".join(parts)
    else:
        overall_score = None
        is_partial = True
        coverage_label = "No Valid Categories Measured"
        coverage_warning = "All requested audit checks failed or returned no data."

    return {
        "overall_score": overall_score,
        "is_partial": is_partial,
        "coverage_label": coverage_label,
        "coverage_warning": coverage_warning,
        "tested_categories_count": tested_count,
        "total_categories_count": 4,
    }


@app.post("/api/audit")
def audit(req: AuditPayload) -> JSONResponse:
    try:
        from agent.tools import (
            audit_accessibility,
            audit_layout,
            audit_performance_hints,
            audit_typography,
        )
        from agent.url_utils import normalize_url

        valid, normalized_url, err_msg = normalize_url(req.url)
        if not valid:
            return JSONResponse({"error": err_msg, "url": req.url}, status_code=400)

        tool_choice = req.tool.strip().lower()
        all_pillars = ["accessibility", "typography", "layout", "performance"]

        # Determine which pillars to run based on user input
        requested_pillars: set[str] = set()
        if tool_choice in ("all", "full", "full_suite"):
            requested_pillars = set(all_pillars)
            routing_label = "Manual Selection: Full Suite Audit (All 4 Pillars)"
            selected_tool_label = "all"
            routing_type = "full_audit"
        elif tool_choice in ("accessibility", "audit_accessibility"):
            requested_pillars = {"accessibility"}
            routing_label = "Manual Selection: Accessibility Audit (WCAG 2.1)"
            selected_tool_label = "audit_accessibility"
            routing_type = "manual_selection"
        elif tool_choice in ("typography", "audit_typography"):
            requested_pillars = {"typography"}
            routing_label = "Manual Selection: Typography & Readability"
            selected_tool_label = "audit_typography"
            routing_type = "manual_selection"
        elif tool_choice in ("layout", "audit_layout"):
            requested_pillars = {"layout"}
            routing_label = "Manual Selection: Layout & Mobile Responsiveness"
            selected_tool_label = "audit_layout"
            routing_type = "manual_selection"
        elif tool_choice in ("performance", "audit_performance_hints", "performance_hints"):
            requested_pillars = {"performance"}
            routing_label = "Manual Selection: Performance & Assets"
            selected_tool_label = "audit_performance_hints"
            routing_type = "manual_selection"
        else:
            requested_pillars = set(all_pillars)
            routing_label = f"Manual Selection: {tool_choice}"
            selected_tool_label = tool_choice
            routing_type = "manual_selection"

        tool_runners = {
            "accessibility": audit_accessibility,
            "typography": audit_typography,
            "layout": audit_layout,
            "performance": audit_performance_hints,
        }

        results: dict[str, Any] = {}
        all_issues: list[dict[str, Any]] = []

        for pillar_name in all_pillars:
            if pillar_name in requested_pillars:
                runner = tool_runners[pillar_name]
                try:
                    res = runner(normalized_url)
                    if isinstance(res, dict) and "error" in res and "score" not in res:
                        results[pillar_name] = {
                            "status": "failed",
                            "state": "failed",
                            "score": None,
                            "error": res["error"],
                            "issues": [],
                            "issues_count": 0,
                            "status_label": "Audit Failed",
                            "score_basis": res.get("error", "Error executing audit tool"),
                            "checks_performed": [],
                            "checks_not_performed": ["Tool failed during execution"],
                            "evidence": {},
                        }
                    else:
                        score_val = res.get("score")
                        pillar_issues = res.get("issues", [])
                        for iss in pillar_issues:
                            iss_copy = dict(iss)
                            iss_copy["pillar"] = pillar_name
                            all_issues.append(iss_copy)

                        results[pillar_name] = {
                            "status": "tested",
                            "state": "tested",
                            "score": score_val,
                            "issues_count": len(pillar_issues),
                            "issues": pillar_issues,
                            "score_basis": res.get("score_basis", "Static HTML analysis"),
                            "score_caveat": res.get("score_caveat", ""),
                            "checks_performed": res.get("checks_performed", []),
                            "checks_not_performed": res.get("checks_not_performed", []),
                            "evidence": res.get("evidence", {}),
                            "status_label": f"Tested & Scored ({score_val}/100)",
                        }
                except Exception as runner_err:
                    results[pillar_name] = {
                        "status": "failed",
                        "state": "failed",
                        "score": None,
                        "error": str(runner_err),
                        "issues": [],
                        "issues_count": 0,
                        "status_label": "Audit Failed",
                        "score_basis": f"Tool error: {str(runner_err)[:100]}",
                        "checks_performed": [],
                        "checks_not_performed": ["Tool execution error"],
                        "evidence": {},
                    }
            else:
                # Explicitly marked as not tested - never treat as 0 or 100!
                results[pillar_name] = {
                    "status": "not_tested",
                    "state": "not_tested",
                    "score": None,
                    "issues_count": 0,
                    "issues": [],
                    "status_label": "Not Tested in This Run",
                    "score_basis": "Excluded from current audit scope",
                    "score_caveat": "Category was not requested; run Full Suite to measure this pillar.",
                    "checks_performed": [],
                    "checks_not_performed": ["Category was excluded from this audit selection"],
                    "evidence": {},
                }

        score_data = _calculate_audit_score(results)

        return JSONResponse({
            "url": normalized_url,
            "url_normalized": normalized_url,
            "overall_score": score_data["overall_score"],
            "is_partial": score_data["is_partial"],
            "coverage_count": score_data["tested_categories_count"],
            "tested_categories_count": score_data["tested_categories_count"],
            "total_categories": 4,
            "total_categories_count": 4,
            "coverage_label": score_data["coverage_label"],
            "coverage_warning": score_data["coverage_warning"],
            "results": results,
            "total_issues": len(all_issues),
            "issues": all_issues,
            "routing": {
                "routing_type": routing_type,
                "routing_label": routing_label,
                "selected_tool": selected_tool_label,
                "tool_selected": selected_tool_label,
                "description": routing_label,
                "model_decision": False,
                "notice": "Initiated via direct manual user selection. Strands Decider 2B was bypassed for manual execution.",
            },
        })
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {str(e)}"}, status_code=500)
