"""DesignDoctor AI: an intelligent website UI/UX audit agent.

Strands Decider 2B selects the right audit tool for each user request (tool selection
pattern). The LLM (Amazon Bedrock / UGMdu) interprets the structured audit results and
writes human-readable findings and improvement suggestions.

    from agent.agent import HackathonAgent
    out = HackathonAgent().chat("Audit the accessibility of https://example.com")
    print(out["reply"])
    print(out["decisions"])   # one record per Decider call, with probabilities and confidence
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from strands import Agent

from decider_kit import Decider
from decider_kit.llm import agent_model, default_model_id, strip_thinking

from .decision import AuditToolSelector
from .tools import TOOLS

NAME = "DesignDoctor AI"

# How long to wait for a single LLM turn before giving up.
# UGMdu LLM has been seen to hang indefinitely; we fail fast and surface a clear error.
_LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "90"))

SYSTEM_PROMPT = """You are DesignDoctor AI, an expert website UI/UX auditor.

When a user gives you a URL to audit, call the appropriate audit tool to gather evidence, then report the findings using this structure:

## Audit Results: <tool name>
**Score:** X/100 (based on N/M checks — static HTML analysis only)

### Issues Found
For each issue:
- **[SEVERITY] Category** — Finding. Fix: suggestion. WCAG: reference.

### What Was Checked
List the checks_performed from the tool result.

### What Could Not Be Verified
List the checks_not_performed from the tool result — always include this section.

### Top 3 Recommendations
Numbered list of the highest-impact fixes.

---
Rules you must follow:
- Use only scores and findings from the tool result. Never invent numbers.
- Always include the "What Could Not Be Verified" section — this is essential honesty.
- Never claim a website is "fully accessible" or "passes WCAG" from static HTML analysis alone.
- If a URL is blocked or unreachable, say so clearly.
- For general UI/UX questions (no URL), answer directly without calling a tool.
- Keep responses concise and actionable.
"""


class _LLMTimeoutError(Exception):
    """Raised when the LLM call exceeds _LLM_TIMEOUT_S."""


def _run_with_timeout(fn, timeout_s: float):
    """Run fn() in a thread; raise _LLMTimeoutError if it takes longer than timeout_s."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        try:
            return future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            raise _LLMTimeoutError(
                f"LLM did not respond within {timeout_s:.0f}s. "
                "The upstream LLM service may be temporarily unavailable."
            )


class HackathonAgent:
    """One Strands agent per session, with AuditToolSelector wired in for tool selection."""

    def __init__(self, decider: Decider | None = None, model_id: str | None = None, eager: bool | None = None):
        self.decider = decider or Decider()
        self.model_id = model_id or default_model_id()
        self.eager = False
        # Build the model once and reuse it — avoids re-initialising the client on every turn
        self._model = agent_model(self.model_id)
        self.sessions: dict[str, dict[str, Any]] = {}

    def _session(self, session_id: str) -> dict[str, Any]:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "selector": AuditToolSelector(self.decider),
                "history": "",
            }
        return self.sessions[session_id]

    def chat(self, message: str, session_id: str = "default", images: list[Any] | None = None) -> dict[str, Any]:
        """Run one user turn. Returns reply, decisions, model_id, latency_ms."""
        sess = self._session(session_id)
        selector: AuditToolSelector = sess["selector"]
        before = len(selector.log)

        t0 = time.perf_counter()

        # ── Step 1: Strands Decider 2B picks the tool (fast, ~1.5s) ──────────
        # This runs before the LLM, so the Decider result always appears even
        # if the LLM later times out.
        try:
            tools = selector.tools_for(message, sess["history"])
        except Exception as dec_err:
            # Decider failure is uncommon; fall back to all tools and surface the warning
            tools = TOOLS
            selector.log.append({
                "stage": "tool_selection",
                "tool": "all (decider error)",
                "confidence": 0.0,
                "narrowed": False,
                "error": str(dec_err)[:120],
                "decider_ms": 0,
            })

        decisions_before_llm = selector.log[before:]

        # ── Step 2: LLM turn with explicit timeout ────────────────────────────
        agent = Agent(
            model=self._model,
            system_prompt=SYSTEM_PROMPT,
            tools=tools if tools else TOOLS,
            callback_handler=None,
        )

        try:
            result = _run_with_timeout(lambda: agent(message), _LLM_TIMEOUT_S)
            reply = strip_thinking(str(result))
        except _LLMTimeoutError as te:
            provider = os.environ.get("LLM_PROVIDER", "bedrock")
            reply = (
                f"**Service temporarily unavailable**\n\n"
                f"The {provider} LLM did not respond within {_LLM_TIMEOUT_S:.0f}s — "
                "the upstream inference service appears to be overloaded or down.\n\n"
                "**What you can do:**\n"
                "- Wait 30–60 seconds and try again\n"
                "- If using the UGMdu cloud (`LLM_PROVIDER=ugmdu`), the free-tier GPU may be busy — try again shortly\n"
                "- Switch to Amazon Bedrock: set `LLM_PROVIDER=bedrock` in `.env` and restart the demo\n\n"
                "**Note:** The Strands Decider 2B is working normally — the decision panel shows "
                "it successfully routed your request before the LLM timed out."
            )
        except Exception as llm_err:
            err_str = str(llm_err)
            # Detect CloudFront/gateway HTML leaking through the Strands OpenAI client
            if "<html" in err_str.lower() or "504" in err_str or "502" in err_str or "cloudfront" in err_str.lower():
                provider = os.environ.get("LLM_PROVIDER", "bedrock")
                reply = (
                    f"**Gateway error from {provider} LLM (504/502)**\n\n"
                    "The upstream LLM API returned a gateway error (CloudFront 504). "
                    "This means the inference backend is temporarily unavailable.\n\n"
                    "**What you can do:**\n"
                    "- Wait a minute and try again\n"
                    "- Switch to Amazon Bedrock: set `LLM_PROVIDER=bedrock` in `.env`\n\n"
                    "The Strands Decider 2B decision is shown in the right panel — it ran successfully."
                )
            else:
                reply = (
                    f"**LLM error:** {type(llm_err).__name__}: {err_str[:200]}\n\n"
                    "The audit tool data was collected. Try again or switch LLM provider in `.env`."
                )

        # Update session history (even on failure, so next turn has context)
        sess["history"] = (sess["history"] + f"\nUser: {message}\nAssistant: {reply[:300]}")[-2000:]

        return {
            "reply": reply,
            "decisions": selector.log[before:],
            "model_id": self.model_id,
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "agent": NAME,
            "eager": self.eager,
        }


if __name__ == "__main__":
    import sys

    a = HackathonAgent()
    msgs = sys.argv[1:] or [
        "Audit the accessibility of https://example.com",
        "Now check the layout too.",
    ]
    for msg in msgs:
        out = a.chat(msg)
        print(f"\n--- {msg} ---")
        print("REPLY:", out["reply"][:600])
        print("DECISIONS:", json.dumps(out["decisions"], indent=2))
        print(f"Latency: {out['latency_ms']} ms")
