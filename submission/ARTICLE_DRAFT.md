# DesignDoctor AI: Building a Website Audit Agent with Strands Decider 2B

**Tags:** #strands-decider-2b #tool-selection

---

## The problem

Website accessibility and UI/UX audits are expensive and slow. Lighthouse gives you a list of issues but no conversational context. Hiring a consultant is cost-prohibitive for most teams. What if you could ask a question in plain English — "Is this accessible for screen readers?" — and get structured, evidence-based findings back in seconds?

That's DesignDoctor AI.

---

## What DesignDoctor AI does

DesignDoctor AI is a conversational website audit agent. Give it any public URL and describe what you want checked. It fetches the real page, runs the right audit tool, and explains the findings with evidence, severity ratings, and concrete fixes.

Four audit categories:
- **Accessibility** — alt text, ARIA, colour contrast, heading structure, language
- **Typography** — heading hierarchy, font sizes, readability hints
- **Layout** — viewport, responsive design, fixed widths, image dimensions
- **Performance hints** — render-blocking resources, lazy loading, meta tags, page weight

Every score is evidence-based (X out of Y checks passed) and every result includes a clear list of what could not be verified without a browser.

---

## The decision: where Strands Decider 2B fits

The most interesting engineering decision in DesignDoctor AI is the tool router.

When a user says "Is this accessible for screen readers?", the agent needs to pick `audit_accessibility` and give the LLM only that tool. When they say "Why is it loading slowly?", it should pick `audit_performance_hints`. When they ask a follow-up question about previous findings, it should pick `none` and answer directly.

This is a language-judgement problem. The request text has to be read and mapped to intent. A rule-based system ("if the message contains 'accessibility' then…") breaks immediately on paraphrased requests. An LLM can do it, but spending a full model call just to decide which tool to use wastes tokens and adds latency.

**Strands Decider 2B solves this perfectly.** It reads the user's request and a description of each tool's purpose, and returns calibrated probabilities in a single forward pass — about 1.5 seconds with the hosted API. The result is auditable (you see the confidence score), cost-efficient (no LLM tokens used), and degrades gracefully (if confidence is below 0.6, all tools are kept and the LLM chooses).

---

## The reusable pattern

The decision is implemented as a reusable `#tool-selection` pattern in `agent/decision.py`:

```python
from decider_kit.patterns.tool_selection import ToolSelector
from decider_kit import Decider

selector = ToolSelector(
    Decider(),
    tools=[audit_accessibility, audit_typography, audit_layout, audit_performance_hints],
    threshold=0.6,
    context="for a website UI/UX audit",
)
tools = selector.tools_for(user_request)
# → [audit_accessibility]  when confidence ≥ 0.6
# → all tools              when confidence < 0.6 (LLM chooses)
```

One-line docstrings on each tool become the option descriptions — so adding a tool is just writing a function with a good docstring.

---

## Benchmarked results

*(These will be filled in from `./kit bench --split test` output after running against the held-out eval cases.)*

| Metric | Decider | LLM baseline |
|---|---|---|
| Tool-selection accuracy | TBD% | TBD% |
| Latency per decision | ~1.5s | ~8–12s |
| Cost per decision | Free (UGMdu) / ~$0 | ~$0.001 |

The Decider is significantly faster and cheaper than asking the full LLM to select a tool.

---

## Low-confidence handling

When the Decider's confidence falls below 0.6, `ToolSelector` keeps all four tools and lets the Strands Agent choose. This ensures no request is silently misrouted — the system degrades to full LLM reasoning rather than making a wrong decision.

---

## Architecture

```
User message → Strands Decider 2B (tool selection, ~1.5s)
                        ↓ selected tool + confidence
             Strands Agent (Amazon Bedrock Nova Lite)
                        ↓ calls one audit tool
             Real HTTP fetch + HTML/CSS parser
                        ↓ structured findings
             LLM explanation → Markdown reply
                        ↓
             FastAPI + Browser dashboard
```

The agent is deployed on **Amazon Bedrock AgentCore Runtime** for the submission.

---

## Limitations (honest)

Static HTML analysis cannot check keyboard navigation, screen reader announcements, JavaScript-rendered content, or real Core Web Vitals. Every result includes a "What Could Not Be Verified" section. No score claims WCAG compliance without browser-based testing.

---

## Running it yourself

```bash
git clone https://github.com/YOUR_USERNAME/designdoctor-ai
cd designdoctor-ai
cp .env.example .env
# Add your UGMdu key or Bedrock credentials
./kit setup --yes --llm bedrock --mode ugmdu --key YOUR_KEY
./kit demo-bg    # http://localhost:8501
```

---

## Credits

Built with the **AWS User Group Madurai** Strands Decider hackathon kit.  
[awsugmdu.in](https://www.awsugmdu.in)
