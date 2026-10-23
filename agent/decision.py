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
    """Wraps ToolSelector; exposes the `.log` list the demo UI reads from `decisions`."""

    def __init__(self, decider: Decider, threshold: float = 0.6):
        self._selector = ToolSelector(
            decider,
            TOOLS,
            threshold=threshold,
            context="for a website UI/UX audit",
        )

    @property
    def log(self) -> list[dict[str, Any]]:
        return self._selector.log

    def tools_for(self, request: str, history: str = "") -> list[Any]:
        """Return the narrowed tool list (or all tools if confidence is below threshold)."""
        return self._selector.tools_for(request, history)

    def last_selection(self) -> dict[str, Any] | None:
        return self._selector.log[-1] if self._selector.log else None
