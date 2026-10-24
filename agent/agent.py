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

    def chat(self, message: str, session_id: str = "default", images: list[Any] | None = None, url: str | None = None) -> dict[str, Any]:
        """Run one user turn. Returns reply, decisions, model_id, latency_ms."""
        sess = self._session(session_id)
        selector: AuditToolSelector = sess["selector"]
        before = len(selector.log)

        t0 = time.perf_counter()

        # -- Step 1: Strands Decider 2B picks the tool (fast, ~1.5s) ----------
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

        # -- Step 2: LLM turn with explicit timeout ----------------------------
        # Extract target URL from message or session
        target_url = url or self._extract_url_from_message(message) or sess.get("active_url")
        if target_url:
            sess["active_url"] = target_url

        reply = ""
        served_by = ""
        guidance_type = "llm"

        try:
            agent = Agent(
                model=self._model,
                system_prompt=SYSTEM_PROMPT,
                tools=tools if tools else TOOLS,
                callback_handler=None,
            )
            result = _run_with_timeout(lambda: agent(message), _LLM_TIMEOUT_S)
            reply = strip_thinking(str(result))
            provider = os.environ.get("LLM_PROVIDER", "bedrock")
            served_by = f"{provider.capitalize()} LLM ({self.model_id})"
        except Exception as llm_err:
            # LLM is unconfigured, timed out, or encountered a credentials/network error.
            # In accordance with hackathon honesty rules, generate trustworthy rule-based
            # audit guidance directly from deterministic tool results instead of failing.
            reply, served_by, guidance_type = self._fallback_guidance(message, tools, target_url)

        # Update session history (so next turn has context)
        sess["history"] = (sess["history"] + f"\nUser: {message}\nAssistant: {reply[:300]}")[-2000:]

        return {
            "reply": reply,
            "decisions": selector.log[before:],
            "model_id": self.model_id,
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "agent": NAME,
            "eager": self.eager,
            "served_by": served_by,
            "guidance_type": guidance_type,
        }

    def _extract_url_from_message(self, message: str) -> str | None:
        """Extract a valid target URL from the user message."""
        import re
        from agent.url_utils import normalize_url

        # Match http/https URLs or domain names
        matches = re.findall(r"(?:https?://[^\s'\"<>()]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s'\"<>()]*)?)", message)
        for cand in matches:
            cand = cand.strip(".,;:?!")
            # Exclude known false positives (system names, file extensions)
            if cand.lower().endswith((".py", ".md", ".json", ".css", ".js", ".png", ".jpg")):
                continue
            if "designdoctor" in cand.lower() or "decider" in cand.lower():
                continue
            is_valid, norm, _ = normalize_url(cand, check_dns=False)
            if is_valid:
                return norm
        return None

    def _fallback_guidance(self, message: str, tools: list[Any], target_url: str | None) -> tuple[str, str, str]:
        """Generate structured deterministic rule-based audit guidance when LLM is unavailable."""
        from agent.tools import (
            audit_accessibility,
            audit_layout,
            audit_performance_hints,
            audit_typography,
        )

        served_by = "DesignDoctor Static Engine (Rule-based)"
        guidance_type = "rule_based_engine"

        # If a target URL is available, execute the deterministic audit tool
        if target_url:
            # Pick the primary tool
            tool_fn = audit_accessibility
            if tools and len(tools) == 1:
                tool_fn = tools[0]
            else:
                m = message.lower()
                if any(k in m for k in ["typo", "font", "heading", "readab"]):
                    tool_fn = audit_typography
                elif any(k in m for k in ["layout", "mobile", "viewport", "responsive", "overflow"]):
                    tool_fn = audit_layout
                elif any(k in m for k in ["perf", "speed", "fast", "slow", "script", "asset", "blocking"]):
                    tool_fn = audit_performance_hints
                else:
                    tool_fn = audit_accessibility

            try:
                raw_res = tool_fn(target_url)
                if isinstance(raw_res, str):
                    try:
                        raw_res = json.loads(raw_res)
                    except Exception:
                        pass
                if isinstance(raw_res, dict):
                    report = self._format_audit_report(tool_fn, raw_res, target_url)
                    return report, served_by, guidance_type
            except Exception as e:
                return (
                    f"> **Audit Error:** Could not execute `{getattr(tool_fn, '__name__', 'audit')}` on `{target_url}`: {e}",
                    served_by,
                    "error",
                )

        # If no target URL, return helpful UI/UX design guidance
        general_guidance = self._format_general_guidance(message)
        return general_guidance, served_by, "rule_based_guidance"

    def _format_audit_report(self, tool_fn: Any, res: dict[str, Any], url: str) -> str:
        """Format raw audit tool output into standard DesignDoctor AI Markdown report."""
        if res.get("error"):
            return (
                f"> **Audit Notice:** Could not inspect `{url}`.\n\n"
                f"**Reason:** {res['error']}\n\n"
                "**What you can do:**\n"
                "- Verify that the URL is public and currently reachable via HTTPS\n"
                "- Private, local, and internal network IP addresses are blocked for safety\n"
                "- Enter a valid public website (e.g. `https://example.com` or `stripe.com`)"
            )

        tool_name = getattr(tool_fn, "__name__", "audit")
        score = res.get("score")
        score_basis = res.get("score_basis", "static HTML analysis only")
        score_display = f"{score}/100" if isinstance(score, (int, float)) else "—/100"

        issues = res.get("issues", [])
        performed = res.get("checks_performed", [])
        unverified = res.get("checks_not_performed", [])

        lines = [
            "> **Automated Guidance (Rule-Based Engine)**",
            "> Generative LLM inference is currently unconfigured or offline. The audit findings and remediations below were compiled deterministically from DesignDoctor's static HTML diagnostic engine.",
            "",
            f"## Audit Results: {tool_name}",
            f"**Score:** {score_display} ({score_basis})",
            f"**Target URL:** `{url}`",
            "",
            "### Issues Found",
        ]

        if issues:
            for iss in issues:
                sev = str(iss.get("severity", "info")).upper()
                cat = iss.get("category", "General")
                finding = iss.get("finding", "")
                fix = iss.get("fix", "Review element structure.")
                wcag = iss.get("wcag", "")
                wcag_str = f" WCAG: {wcag}" if wcag else ""
                lines.append(f"- **[{sev}] {cat}** — {finding} Fix: {fix}.{wcag_str}")
        else:
            lines.append("- **[PASS] No critical or warning issues detected** across measured static HTML checks.")

        lines.append("")
        lines.append("### What Was Checked")
        if performed:
            for chk in performed:
                lines.append(f"- {chk}")
        else:
            lines.append("- Static DOM element parsing and attribute validation")

        lines.append("")
        lines.append("### What Could Not Be Verified")
        if unverified:
            for chk in unverified:
                lines.append(f"- {chk}")
        else:
            lines.append("- Dynamic JavaScript runtime rendering (requires full headless browser automation)")
            lines.append("- Assistive hardware interactions (requires real screen reader evaluation)")

        lines.append("")
        lines.append("### Top 3 Recommendations")
        recs = []
        for iss in issues:
            if iss.get("fix") and iss["fix"] not in recs:
                recs.append(iss["fix"])
            if len(recs) >= 3:
                break

        if not recs:
            if "accessib" in tool_name:
                recs = [
                    "Verify manual keyboard tab order and focus rings across all interactive controls.",
                    "Inspect color contrast of styled elements in real viewport conditions.",
                    "Test primary navigation flows with an active screen reader (NVDA, VoiceOver).",
                ]
            elif "typo" in tool_name:
                recs = [
                    "Ensure clean heading progression (H1 -> H2 -> H3) without skipping hierarchy levels.",
                    "Maintain optimal line length between 45 and 75 characters for reading comfort.",
                    "Add descriptive meta description tags to boost search discoverability.",
                ]
            elif "layout" in tool_name:
                recs = [
                    "Verify that the viewport meta tag does not disable pinch-to-zoom.",
                    "Test breakpoint behavior across small mobile viewports (320px - 375px).",
                    "Ensure horizontal overflow is prevented across all container elements.",
                ]
            else:
                recs = [
                    "Defer non-critical third-party JavaScript files using async or defer.",
                    "Specify explicit width and height attributes on all image elements to prevent CLS.",
                    "Enable native lazy loading (loading='lazy') on below-the-fold assets.",
                ]

        for i, r in enumerate(recs[:3], 1):
            lines.append(f"{i}. {r}")

        return "\n".join(lines)

    def _format_general_guidance(self, message: str) -> str:
        """Provide informative UI/UX guidance for general queries without a URL."""
        m = message.lower()
        if any(k in m for k in ["contrast", "color", "colour", "wcag", "ratio"]):
            return (
                "> **Automated Guidance (Rule-Based Engine)**\n"
                "> Generative LLM inference is currently unconfigured. Below is DesignDoctor's guidance for WCAG color contrast standards.\n\n"
                "## WCAG 2.1 Contrast Standards\n"
                "- **Normal text (<18pt / <14pt bold):** Requires minimum **4.5:1** contrast ratio (WCAG 1.4.3 Level AA).\n"
                "- **Large text (>=18pt or >=14pt bold):** Requires minimum **3.0:1** contrast ratio.\n"
                "- **UI components & graphical objects:** Requires minimum **3.0:1** against adjacent colors (WCAG 1.4.11 Level AA).\n"
                "- **Enhanced contrast (Level AAA):** Requires **7.0:1** for normal text and **4.5:1** for large text.\n\n"
                "### Recommended Action\n"
                "Enter a public URL in the audit bar or prompt (e.g. `Audit accessibility for https://example.com`) to inspect real contrast pairs."
            )
        elif any(k in m for k in ["typo", "font", "heading", "h1", "hierarchy"]):
            return (
                "> **Automated Guidance (Rule-Based Engine)**\n"
                "> Generative LLM inference is currently unconfigured. Below is DesignDoctor's typography guidelines.\n\n"
                "## Typography & Readability Best Practices\n"
                "- **Heading Hierarchy:** Maintain a single `<h1>` representing the page topic, followed by sequential `<h2>` and `<h3>` tags without skipping levels.\n"
                "- **Line Length:** Target 45--75 characters per line (approx. 60--70ch) for optimal scanability.\n"
                "- **Line Height:** Use 1.4--1.6 for body copy and 1.1--1.25 for large display headings.\n"
                "- **Relative Units:** Use `rem` and `em` instead of fixed `px` to respect user browser font size preferences.\n\n"
                "### Recommended Action\n"
                "Run a typography audit by prompting `Check typography for https://example.com`."
            )
        elif any(k in m for k in ["mobile", "responsive", "viewport", "layout", "phone"]):
            return (
                "> **Automated Guidance (Rule-Based Engine)**\n"
                "> Generative LLM inference is currently unconfigured. Below is DesignDoctor's mobile layout guidance.\n\n"
                "## Mobile Layout & Viewport Standards\n"
                "- **Viewport Meta Tag:** Always specify `<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">`.\n"
                "- **Never disable zoom:** Avoid `user-scalable=no` or `maximum-scale=1.0` (WCAG 1.4.4 Resize Text).\n"
                "- **Touch Target Sizing:** Minimum 44x44 CSS pixels for interactive buttons and links (WCAG 2.5.5 / 2.5.8).\n"
                "- **Horizontal Scrolling:** Never let content or images overflow the mobile viewport width (320px--375px).\n\n"
                "### Recommended Action\n"
                "Test a website layout with `Is https://example.com responsive?`."
            )
        else:
            return (
                "> **Automated Guidance (Rule-Based Engine)**\n"
                "> Generative LLM inference is currently unconfigured. DesignDoctor AI is ready to audit your websites.\n\n"
                "## How to Audit with DesignDoctor AI\n"
                "To audit a website, provide a public URL or click any suggested prompt below:\n\n"
                "- `Audit the accessibility of https://example.com`\n"
                "- `Check typography and heading structure for https://example.com`\n"
                "- `Test mobile responsiveness for https://example.com`\n"
                "- `Summarise top 3 fixes for https://example.com`\n\n"
                "**Strands Decider 2B** routes each query to the exact audit tool needed, and our static diagnostics engine evaluates real HTML DOM evidence."
            )


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
