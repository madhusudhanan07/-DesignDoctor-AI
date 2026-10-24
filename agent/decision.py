"""REUSABLE DECISION PATTERN: website audit tool selection  (#tool-selection)

What it does
    Before each audit step, Strands Decider 2B reads the user's request and a one-line
    description of the website under audit, then picks which specialised audit tool to
    run next. Fewer tools in the agent's context means fewer wrong calls and cheaper
    LLM turns. When the decider is unsure (confidence below threshold), all audit tools
    are kept and the LLM chooses.

    The four audit tools are:
    - audit_accessibility: ARIA labels, alt text, colour contrast, keyboard nav hints
    - audit_typography: font sizes, heading hierarchy, line-height, readability score
    - audit_layout: responsive design, viewport, spacing, fixed widths, media queries
    - audit_performance_hints: render-blocking scripts/CSS, lazy loading, meta tags, HTML weight

Typed questions and options
    tool (choice): one option per audit tool, described by the tool's own docstring, plus
    "none" ("no audit tool needed; answer from findings already gathered").

Wiring
    `AuditToolSelector` wraps `ToolSelector` from `decider_kit.patterns.tool_selection`.
    It is called in `HackathonAgent._session()` and in `chat()` before each Strands Agent
    turn. The `.log` attribute accumulates one record per decision, which `chat()` returns
    in `decisions`.

    from decider_kit.patterns.tool_selection import ToolSelector
    from decider_kit import Decider
    selector = AuditToolSelector(Decider())
    tools = selector.tools_for(user_message)
    agent = Agent(model=..., tools=tools, ...)
    # selector.log[-1] holds the verdict for the decisions list

How to reuse this pattern
    1. Replace TOOLS with your own @tool functions (keep clear one-line docstrings).
    2. Adjust `threshold` if needed (default 0.6: confident decisions narrow the tool set;
       unsure decisions keep all tools and let the LLM choose).
    3. The `QUESTIONS` dict is shown here for documentation; ToolSelector builds the
       actual question dynamically from your tools at call time. Use QUESTIONS in
       eval_cases.jsonl to document the expected labels.
"""

from __future__ import annotations

from typing import Any

from decider_kit import Decider
from decider_kit.patterns.tool_selection import ToolSelector

from .tools import TOOLS

PATTERN_TAG = "#tool-selection"

# QUESTIONS is documented here for the benchmark; the actual question is built dynamically
# by ToolSelector.questions_for() at call time, using each tool's one-line docstring.
QUESTIONS = {
    "tool": Decider.choice(
        "Which audit tool should handle this request?",
        {
            "audit_accessibility": "Audit accessibility: ARIA labels, alt text, colour contrast, form labels, keyboard nav hints.",
            "audit_typography": "Audit typography: font sizes, heading hierarchy, line-height, readability, and text density.",
            "audit_layout": "Audit layout: responsive design, viewport meta, spacing, overflow, and structural patterns.",
            "audit_performance_hints": "Audit performance hints: render-blocking resources, image lazy-loading, meta tags, and page weight.",
            "none": "No audit tool is needed; answer directly from findings already gathered.",
        },
    )
}


class AuditToolSelector:
    """Wraps ToolSelector; exposes the `.log` list the demo UI reads from `decisions`.

    When the Strands Decider 2B server is available, it provides genuine neural tool selection.
    If the Decider endpoint is offline or unavailable, it transparently applies a clear,
    documented keyword heuristic fallback, accurately labeled so the user knows Decider is offline.
    """

    def __init__(self, decider: Decider | None = None, threshold: float = 0.6):
        if decider is None:
            decider = Decider()
        self.decider = decider
        self._selector = ToolSelector(
            decider,
            TOOLS,
            threshold=threshold,
            context="for a website UI/UX audit",
        )

    @property
    def log(self) -> list[dict[str, Any]]:
        return self._selector.log

    def select_audit_tool(self, request: str) -> dict[str, Any]:
        """Convenience method to route a request and return the structured decision record."""
        self.tools_for(request)
        return self.log[-1] if self.log else {
            "stage": "tool_selection",
            "tool": "none",
            "confidence": 0.5,
            "narrowed": False,
            "routing_mode": "fallback",
        }

    def _heuristic_route(self, request: str) -> tuple[str, float, dict[str, float]]:
        """Transparent heuristic classifier used strictly when Strands Decider 2B service is offline."""
        lower = request.lower()

        # Summary or recommendations from prior findings
        if any(k in lower for k in ("summary", "summarise", "summarize", "top 3", "top 5", "recommendation", "recommend", "advice", "what should i fix", "priorit")):
            return "none", 0.85, {
                "none": 0.85,
                "audit_accessibility": 0.04,
                "audit_typography": 0.04,
                "audit_layout": 0.04,
                "audit_performance_hints": 0.03,
            }

        # Accessibility checks
        if any(k in lower for k in ("accessib", "a11y", "aria", "contrast", "alt text", "wcag", "screen reader", "color contrast")):
            return "audit_accessibility", 0.88, {
                "audit_accessibility": 0.88,
                "audit_typography": 0.04,
                "audit_layout": 0.04,
                "audit_performance_hints": 0.02,
                "none": 0.02,
            }

        # Typography & headings
        if any(k in lower for k in ("typograph", "font", "heading", "readab", "line-height", "font-size", "hierarchy", "text density")):
            return "audit_typography", 0.86, {
                "audit_typography": 0.86,
                "audit_accessibility": 0.04,
                "audit_layout": 0.05,
                "audit_performance_hints": 0.03,
                "none": 0.02,
            }

        # Layout & mobile responsiveness
        if any(k in lower for k in ("layout", "mobile", "phone", "responsive", "overflow", "viewport", "broken on", "screen size", "tablet")):
            return "audit_layout", 0.87, {
                "audit_layout": 0.87,
                "audit_typography": 0.04,
                "audit_accessibility": 0.04,
                "audit_performance_hints": 0.03,
                "none": 0.02,
            }

        # Performance & assets
        if any(k in lower for k in ("performance", "speed", "slow", "asset", "blocking", "render", "lazy", "weight", "kb", "load time")):
            return "audit_performance_hints", 0.84, {
                "audit_performance_hints": 0.84,
                "audit_layout": 0.05,
                "audit_accessibility": 0.04,
                "audit_typography": 0.04,
                "none": 0.03,
            }

        # Default fallback: keep all tools
        return "all", 0.50, {
            "audit_accessibility": 0.25,
            "audit_typography": 0.25,
            "audit_layout": 0.25,
            "audit_performance_hints": 0.25,
            "none": 0.00,
        }

    def tools_for(self, request: str, history: str = "") -> list[Any]:
        """Return the narrowed tool list (or all tools if confidence is below threshold)."""
        # Check if hosted mode is active but credentials are missing
        if self.decider.hosted and (not self.decider.api_key or self.decider.api_key == "your_ugmdu_key_here"):
            tool_name = self._heuristic_route(request)[0]
            entry = {
                "stage": "tool_selection",
                "tool": tool_name,
                "confidence": None,  # Strictly None: never present heuristic match as AI model confidence
                "narrowed": tool_name not in ("all", "none"),
                "routing_mode": "heuristic_fallback",
                "model_routed": False,
                "decider_status": "unconfigured",
                "endpoint": self.decider.url,
                "reason": (
                    f"Hosted Strands Decider 2B endpoint configured ({self.decider.url}), "
                    "but DECIDER_API_KEY is not configured in .env. "
                    "Rule-based keyword heuristic fallback applied."
                ),
                "probabilities": {},
                "decider_ms": 1,
            }
            self._selector.log.append(entry)
            if tool_name == "none":
                return []
            if tool_name in self._selector.by_name:
                return [self._selector.by_name[tool_name]]
            return list(TOOLS)

        try:
            tools = self._selector.tools_for(request, history)
            if self._selector.log:
                last = self._selector.log[-1]
                last["routing_mode"] = "decider_model"
                last["model_routed"] = True
                last["decider_status"] = "connected"
                last["endpoint"] = self.decider.url
                last["reason"] = f"Strands Decider 2B model neural decision: routed to {last.get('tool')} with {round((last.get('confidence') or 0) * 100)}% confidence."
            return tools
        except Exception as dec_err:
            err_msg = str(dec_err)
            tool_name = self._heuristic_route(request)[0]
            if "401" in err_msg:
                status = "auth_error"
                reason = f"Hosted Decider API returned 401 (invalid/expired DECIDER_API_KEY). Rule-based heuristic fallback active."
            elif "402" in err_msg:
                status = "quota_exhausted"
                reason = "Hosted Decider API quota reached. Rule-based heuristic fallback active."
            else:
                status = "offline"
                reason = f"Strands Decider service ({self.decider.url}) unreachable: {err_msg[:80]}. Rule-based heuristic fallback active."

            entry = {
                "stage": "tool_selection",
                "tool": tool_name,
                "confidence": None,  # Rule 8: Do not present heuristic scores as genuine AI model confidence
                "narrowed": tool_name not in ("all", "none"),
                "routing_mode": "heuristic_fallback",
                "model_routed": False,
                "decider_status": status,
                "endpoint": self.decider.url,
                "reason": reason,
                "probabilities": {},
                "decider_ms": 1,
            }
            self._selector.log.append(entry)

            if tool_name == "none":
                return []
            if tool_name in self._selector.by_name:
                return [self._selector.by_name[tool_name]]
            return list(TOOLS)

    def last_selection(self) -> dict[str, Any] | None:
        return self._selector.log[-1] if self._selector.log else None

