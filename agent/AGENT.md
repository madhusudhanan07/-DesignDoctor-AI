# DesignDoctor AI

## Pitch
An intelligent website UI/UX audit agent that inspects any public URL and delivers
evidence-based design improvements across accessibility, typography, layout, and
performance — powered by Strands Decider 2B for smart tool routing.

## Who it is for
Designers, developers, and product teams who want quick, structured feedback on a website's
UI/UX quality without running a full Lighthouse audit or hiring a consultant.

## Features
- Accepts any public URL and fetches real page content via HTTP
- Extracts DOM structure, CSS properties, headings, links, images, and meta tags
- Routes each audit request to the right specialised tool using Strands Decider 2B
- Scores findings by severity (critical / warning / info) with evidence
- Explains every issue in plain language and suggests a concrete fix
- Generates a downloadable structured JSON audit report
- Handles blocked URLs and network failures safely
- Blocks private/internal network addresses

## The decision handed to Strands Decider 2B
**Pattern:** `#tool-selection`

Before each audit step, Strands Decider 2B reads the user's request and decides which
specialised audit tool to invoke:

- `audit_accessibility` — ARIA labels, alt text, colour contrast, keyboard nav
- `audit_typography` — font sizes, line-height, heading hierarchy, readability score
- `audit_layout` — spacing, grid, responsive design, overflow issues
- `audit_performance_hints` — image optimisation, render-blocking assets, meta tags
- `none` — no audit tool needed; answer from findings already gathered

The decider returns calibrated probabilities so the agent can fall back to all tools when
unsure, and the user always sees the confidence score.

## Why a decision model for tool selection
The user's natural-language request ("check the fonts", "is this accessible?",
"why does it look broken on mobile?") requires reading intent — that's a language
judgement, not a rule. Strands Decider 2B makes this faster and cheaper than asking
the full LLM to decide, and provides an auditable confidence score.

## Amazon Bedrock
The LLM (Amazon Nova Lite / UGMdu Qwen3.5-4B during development) interprets the
structured audit results and writes human-readable findings and improvement suggestions.
