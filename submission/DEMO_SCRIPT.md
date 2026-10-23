# DesignDoctor AI — 3-Minute Demo Video Script

**Target:** Amazon Bedrock AgentCore Runtime (`./kit video --target agentcore`)  
**Duration:** ~2:45

---

## [0:00–0:20] Title card + intro narration

> *"DesignDoctor AI — an intelligent website audit agent powered by Strands Decider 2B and Amazon Bedrock. Built for the Agent Experience Hackathon by the AWS User Group Madurai."*

Show: Dashboard loading, URL input visible.

---

## [0:20–0:50] Turn 1 — Accessibility audit

**Type:** `Audit the accessibility of https://example.com`

**Narration:**
> *"The user asks for an accessibility audit. Watch the Strands Decider 2B decision panel — it routes this to the accessibility tool with high confidence in about 1.5 seconds, before the LLM even runs."*

Show: Decider panel populates — tool selected, confidence %, latency.  
Show: Reply arrives with structured findings, score, issues, and the 'What Could Not Be Verified' section.

---

## [0:50–1:20] Turn 2 — Typography

**Type:** `Now check the heading structure and typography`

**Narration:**
> *"A different request — the Decider now routes to the typography tool. Same confidence display, different tool selected."*

Show: New decision card, different tool label.  
Show: Typography findings with heading list and evidence.

---

## [1:20–1:50] Turn 3 — Layout / mobile

**Type:** `Is this page going to look broken on a phone?`

**Narration:**
> *"The Decider reads the intent — 'broken on a phone' maps to the layout audit. No keyword matching, no rules — a genuine language judgement."*

Show: Layout decision card, viewport evidence in the result.

---

## [1:50–2:20] Turn 4 — No tool needed

**Type:** `Summarise the top issues you found across all three audits`

**Narration:**
> *"When no new audit tool is needed, the Decider returns 'none' and the LLM answers directly from prior findings. The agent knows when not to call a tool."*

Show: Decision card shows 'no tool' verdict.  
Show: LLM summarises previous findings.

---

## [2:20–2:45] Outro

**Narration:**
> *"Four specialised audit tools, one forward pass per routing decision, calibrated confidence the code can act on — Strands Decider 2B keeps DesignDoctor AI fast, cheap, and transparent. Built with the AWS User Group Madurai Strands Decider hackathon kit."*

Show: End card with project name, #strands-decider-2b #tool-selection, awsugmdu.in.

---

## Notes for recording

- Use `./kit video --target agentcore` against the deployed AgentCore agent
- The narration lines above are neutral descriptions; `make_video.py` appends the actual Decider verdict
- No background music, no third-party logos
