# DesignDoctor AI — Submission Checklist

Hackathon: Agent Experience Hackathon: Strands Decider  
Submission deadline: 23 October 2026, 11:59 p.m. PT

---

## Required items

### 1. Agent on AWS ✅ / ⏳
- [ ] `./kit deploy` run successfully
- [ ] `./kit invoke "Audit the accessibility of https://example.com"` returns a real result
- [ ] Deployed ARN recorded in `submission/deployment.json`
- **Uses:** Amazon Bedrock (`us.amazon.nova-lite-v1:0`) + UGMdu hosted Strands Decider 2B
- **Meaningful decision:** `#tool-selection` — routes each audit request to the right tool

### 2. AWS Builder Center article ⏳
- [ ] Draft in `submission/ARTICLE_DRAFT.md` — needs benchmark numbers filled in
- [ ] Published at builder.aws.com
- [ ] Tagged: `#strands-decider-2b` and `#tool-selection`
- [ ] Article URL: _(fill in after publishing)_

### 3. Public GitHub repository ⏳
- [ ] `./kit publish YOUR_REPO_NAME` run
- [ ] Repository is public
- [ ] Apache 2.0 license present (`LICENSE`)
- [ ] README.md complete with reusable pattern documentation
- [ ] Repository URL: _(fill in after publishing)_

### 4. Demo video (under 3 minutes) ⏳
- [ ] `./kit video --target agentcore` recorded
- [ ] Uploaded to YouTube / Vimeo as public
- [ ] No copyrighted music, no third-party trademarks
- [ ] Video URL: _(fill in after recording)_
- Script: `agent/demo_script.yaml`

### 5. Tags ✅
- `#strands-decider-2b`
- `#tool-selection`

### 6. Original agent ✅
- DesignDoctor AI is an original use case (website UI/UX audit)
- `IS_KIT_EXAMPLE` removed from `agent/decision.py`

---

## Submission links (fill in before 23 Oct 11:59 p.m. PT)

| Item | URL |
|---|---|
| Public GitHub repository | |
| AWS Builder Center article | |
| Demo video | |

---

## Final steps before submitting

```bash
# 1. Run benchmark on held-out test split
./kit bench --split test
# → fills submission/bench/results.json and results.md

# 2. Record video against deployed agent
./kit video --target agentcore

# 3. Update ARTICLE_DRAFT.md with real benchmark numbers

# 4. Publish repository
./kit publish YOUR_REPO_NAME

# 5. Publish article on AWS Builder Center with the two tags

# 6. Submit three URLs on the hackathon submission form

# 7. After judging: tear down AWS resources
./kit destroy
```

---

## Build credit

Built with the **AWS User Group Madurai** Strands Decider hackathon kit.  
https://www.awsugmdu.in
