# DesignDoctor AI 🩺

> **An intelligent website UI/UX audit agent powered by Strands Decider 2B and Amazon Bedrock.**

[![Hackathon](https://img.shields.io/badge/Agent%20Experience%20Hackathon-Strands%20Decider-6366F1?style=flat-square)](https://builder.aws.com)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square)](LICENSE)
[![Pattern](https://img.shields.io/badge/Pattern-%23tool--selection-22D3A0?style=flat-square)](#decision-pattern)

Built with the **AWS User Group Madurai** Strands Decider hackathon kit.

---

## What it does

DesignDoctor AI inspects any public website URL and delivers evidence-based UI/UX findings across four audit categories — all in a single conversational turn.

| Audit | What it checks |
|---|---|
| **Accessibility** | Alt text, ARIA labels, colour contrast (inline CSS), link text, language attribute, viewport zoom |
| **Typography** | Heading hierarchy (h1–h6), font sizes in embedded CSS, meta description |
| **Layout** | Viewport meta, fixed pixel widths, overflow, image dimensions, CSS media queries |
| **Performance hints** | Render-blocking scripts/CSS, lazy loading, meta tags, page weight, charset |

Every score is evidence-based (passes / total checks) and every result includes a clear list of **what could not be verified** without a browser — no fabricated data.

---

## The Strands Decider 2B decision

**Pattern tag:** `#tool-selection`

Before each LLM turn, Strands Decider 2B reads the user's natural-language request and routes it to the right audit tool with calibrated confidence:

```
User: "Is this accessible for screen readers?"
  → Decider: audit_accessibility  (confidence 92%, ~1.5s)
  → Agent runs only the accessibility tool
  → LLM explains findings
```

This is a genuine language-judgement problem — "check the fonts" vs "check mobile layout" vs "why is it slow" — not a rule that code can compute. The Decider provides an auditable confidence score, falls back to all tools when unsure, and its decision is always visible in the UI even if the LLM times out.

See [`agent/decision.py`](agent/decision.py) for the reusable pattern.

---

## Architecture

```
User message
    │
    ▼
Strands Decider 2B  ──────────────────────────────────────── #tool-selection
(tool routing, ~1.5s)         ↓ confidence + selected tool
    │
    ▼
Strands Agent (Amazon Bedrock / UGMdu LLM)
    │  ↓ calls narrowed tool set
    ├─ audit_accessibility  ─── real HTTP fetch + HTML parser
    ├─ audit_typography      ─── real HTTP fetch + HTML parser
    ├─ audit_layout          ─── real HTTP fetch + HTML parser
    └─ audit_performance_hints ─ real HTTP fetch + HTML parser
    │
    ▼
Structured audit result  →  LLM explanation  →  Markdown reply
    │
    ▼
FastAPI demo server  →  Browser dashboard (dark SaaS UI)
```

---

## Quickstart

### Prerequisites

- Python 3.12+
- A UGMdu API key (from [awsugmdu.in](https://www.awsugmdu.in)) **or** AWS credentials with Bedrock access

### Setup

```bash
# 1. Clone and enter
git clone https://github.com/YOUR_USERNAME/designdoctor-ai.git
cd designdoctor-ai

# 2. Create and activate venv
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt   # or: ./kit setup

# 4. Configure
cp .env.example .env
# Edit .env — set your LLM_PROVIDER, API keys, and model IDs

# 5. Run setup verification
.\kit.cmd setup --yes --llm ugmdu --mode ugmdu --key YOUR_KEY   # Windows
# ./kit setup --yes --llm bedrock --mode ugmdu --key YOUR_KEY   # Bedrock

# 6. Start the demo
.\kit.cmd demo-bg     # Windows  → http://localhost:8501
# ./kit demo-bg       # macOS/Linux
```

### Configuration (`.env`)

```env
# LLM provider: bedrock | ugmdu | local
LLM_PROVIDER=bedrock

# For Bedrock (required for submission)
BEDROCK_MODEL_ID=us.amazon.nova-lite-v1:0
AWS_REGION=us-east-1
AWS_PROFILE=hackathon

# For UGMdu cloud (development / no-cost)
# LLM_PROVIDER=ugmdu
# LLM_MODEL_ID=gpt-oss-20b
# DECIDER_API_KEY=your_key_here

# Decider (uses same key as UGMdu LLM)
DECIDER_MODE=ugmdu
DECIDER_API_KEY=your_key_here

# LLM timeout (seconds)
LLM_TIMEOUT_S=90
```

---

## Running tests

```bash
.\kit.cmd test          # Windows
# ./kit test            # macOS/Linux

# Or directly:
.venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: **38 tests pass** in ~4 seconds (offline, no external calls).

---

## Benchmark

```bash
.\kit.cmd bench --split tune    # tune the decision questions
.\kit.cmd bench --split test    # measure accuracy on held-out cases
```

Results in `submission/bench/`.

---

## Decision pattern — reuse guide

The reusable pattern lives in [`agent/decision.py`](agent/decision.py).

**Pattern tag:** `#tool-selection`  
**Questions type:** `choice` — one option per tool, described by its docstring  
**Threshold:** 0.6 — below this confidence, all tools are kept and the LLM chooses

```python
from decider_kit.patterns.tool_selection import ToolSelector
from decider_kit import Decider

selector = ToolSelector(
    Decider(),
    tools=[tool1, tool2, tool3],
    threshold=0.6,
    context="for a website UI/UX audit",
)
tools = selector.tools_for(user_request)
agent = Agent(model=..., tools=tools, ...)
```

**To adapt for your agent:**
1. Replace the `tools` list with your own `@tool` functions
2. Give each tool a clear one-line docstring — this becomes the choice option description
3. Adjust `threshold` if needed
4. The `selector.log` contains the full decision record for observability

---

## Deployment to AWS (final submission)

```bash
# Install the AgentCore CLI
.\kit.cmd tools install deploy --yes

# Configure AWS credentials
.\kit.cmd aws-login

# Deploy
.\kit.cmd deploy

# Smoke test
.\kit.cmd invoke "Audit the accessibility of https://example.com"

# Teardown when done
.\kit.cmd destroy
```

The deployed agent uses **Amazon Bedrock** (`us.amazon.nova-lite-v1:0`) and the UGMdu hosted Decider API.

---

## Project structure

```
agent/
  AGENT.md          use case description
  agent.py          HackathonAgent — the main agent class
  decision.py       AuditToolSelector — Strands Decider 2B wiring (#tool-selection)
  tools.py          four audit tools (real HTTP fetch + HTML analysis)
  eval_cases.jsonl  28 labelled cases for the benchmark
  demo_script.yaml  video script
  features.yaml     AgentCore Memory/Gateway config

decider_kit/        reusable library (AWS User Group Madurai)
demo/               FastAPI server + browser dashboard
scripts/            kit tooling
```

---

## Limitations (honest)

Static HTML analysis cannot check:
- Keyboard navigation or focus order (requires browser)
- Screen reader announcements (requires assistive technology)
- Rendered colour contrast from external stylesheets
- JavaScript-rendered content
- Actual Core Web Vitals (LCP, FID, CLS — require browser)
- Visual layout quality

Every audit result includes a "What Could Not Be Verified" section. No score claims full WCAG compliance.

---

## Credits

Built with the **AWS User Group Madurai** Strands Decider hackathon kit.  
Visit [awsugmdu.in](https://www.awsugmdu.in) for the community and events.

Submitted to the **Agent Experience Hackathon: Strands Decider** on AWS Builder Center.  
Tags: `#strands-decider-2b` `#tool-selection`

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
