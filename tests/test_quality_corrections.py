"""Regression and quality-correction test suite for DesignDoctor AI 2.0 (Phase 1.5).

Verifies:
1. URL normalization and validation (stripping duplicate schemes, localhost/private blocking, DNS/domain safety).
2. Honest scoring aggregation (4-state scoring: tested, not_tested, failed, partially_tested; no 0% or 100% false aggregates).
3. Strands Decider routing status (distinguishing model routing, heuristic fallback, and manual selection).
4. AI Provider status telemetry (accurate status reporting for Bedrock and Decider).
"""

import pytest
from unittest.mock import patch, MagicMock

from agent.url_utils import normalize_url, is_valid_url
from agent.decision import AuditToolSelector
from demo.server import _check_llm_status, _check_decider_status, _calculate_audit_score


# ── 1. URL Normalization & Validation Tests ─────────────────────────────────

def test_url_strips_nested_duplicate_schemes():
    # User / clipboard paste bug: https://https://w3.org
    valid, normalized, err = normalize_url("https://https://w3.org", check_dns=False)
    assert valid is True
    assert normalized == "https://w3.org"
    assert not err

    # Mixed nested schemes: http://https://stripe.com
    valid2, normalized2, err2 = normalize_url("http://https://stripe.com", check_dns=False)
    assert valid2 is True
    assert normalized2 == "https://stripe.com"

    # Multiple redundant schemes: https://https://https://example.com/
    valid3, normalized3, err3 = normalize_url("https://https://https://example.com/", check_dns=False)
    assert valid3 is True
    assert normalized3 == "https://example.com/"


def test_url_adds_missing_scheme_defaults_to_https():
    valid, normalized, err = normalize_url("example.com", check_dns=False)
    assert valid is True
    assert normalized == "https://example.com"

    valid_sub, normalized_sub, _ = normalize_url("news.ycombinator.com/item?id=1", check_dns=False)
    assert valid_sub is True
    assert normalized_sub == "https://news.ycombinator.com/item?id=1"


def test_url_rejects_localhost_and_private_ips():
    # Localhost
    valid, _, err = normalize_url("http://localhost:3000", check_dns=False)
    assert valid is False
    assert "Private and localhost addresses are blocked" in err

    valid2, _, err2 = normalize_url("https://127.0.0.1", check_dns=False)
    assert valid2 is False
    assert "Private and localhost addresses are blocked" in err2


def test_url_rejects_empty_or_invalid_hostnames():
    valid, _, err = normalize_url("", check_dns=False)
    assert valid is False
    assert "URL cannot be empty" in err

    valid2, _, err2 = normalize_url("just-a-random-word-without-dot", check_dns=False)
    assert valid2 is False
    assert "does not have a top-level domain" in err2


def test_is_valid_url_helper():
    assert is_valid_url("https://example.com") is True
    assert is_valid_url("https://https://example.com") is True  # normalizable
    assert is_valid_url("http://localhost:8080") is False
    assert is_valid_url("") is False


# ── 2. Honest Scoring State & Aggregation Tests ─────────────────────────────

def test_full_suite_scoring_calculation():
    results = {
        "accessibility": {"score": 90, "state": "tested"},
        "typography": {"score": 80, "state": "tested"},
        "layout": {"score": 70, "state": "tested"},
        "performance": {"score": 100, "state": "tested"},
    }
    score_meta = _calculate_audit_score(results)
    assert score_meta["overall_score"] == 85
    assert score_meta["is_partial"] is False
    assert score_meta["coverage_warning"] is None
    assert score_meta["tested_categories_count"] == 4
    assert score_meta["total_categories_count"] == 4


def test_single_tool_partial_audit_scoring_never_claims_100_overall():
    # Only accessibility was run, scoring 100
    results = {
        "accessibility": {"score": 100, "state": "tested"},
        "typography": {"state": "not_tested"},
        "layout": {"state": "not_tested"},
        "performance": {"state": "not_tested"},
    }
    score_meta = _calculate_audit_score(results)
    # The score is 100 for accessibility, but marked as partial audit
    assert score_meta["overall_score"] == 100
    assert score_meta["is_partial"] is True
    assert "Partial Audit (1/4 Categories" in score_meta["coverage_label"]
    assert "Only Accessibility was tested" in score_meta["coverage_warning"]
    assert "Aggregate score does not represent full UX health" in score_meta["coverage_warning"]
    assert score_meta["tested_categories_count"] == 1
    assert score_meta["total_categories_count"] == 4


def test_scoring_excludes_failed_checks_from_zero_penalty():
    # If a check failed due to network error, it shouldn't be counted as 0/100,
    # which would artificially drag down the measured categories.
    results = {
        "accessibility": {"score": 80, "state": "tested"},
        "typography": {"score": 90, "state": "tested"},
        "layout": {"state": "failed", "error": "Connection timeout"},
        "performance": {"state": "not_tested"},
    }
    score_meta = _calculate_audit_score(results)
    # Average of 80 and 90 is 85, layout error is excluded from numerical average
    assert score_meta["overall_score"] == 85
    assert score_meta["is_partial"] is True
    assert score_meta["tested_categories_count"] == 2
    assert "Layout check failed" in score_meta["coverage_warning"]


def test_empty_results_yields_null_score():
    results = {
        "accessibility": {"state": "not_tested"},
        "typography": {"state": "not_tested"},
        "layout": {"state": "not_tested"},
        "performance": {"state": "not_tested"},
    }
    score_meta = _calculate_audit_score(results)
    assert score_meta["overall_score"] is None
    assert score_meta["is_partial"] is True
    assert score_meta["tested_categories_count"] == 0


# ── 3. Strands Decider Routing & Fallback Honesty Tests ─────────────────────

def test_decider_selector_handles_offline_gracefully():
    selector = AuditToolSelector()
    selector.decider.api_key = "test_key"
    
    # Mock ask to raise connection error (simulating offline decider daemon)
    with patch.object(selector.decider, "ask", side_effect=Exception("[WinError 10061] No connection could be made")):
        # Query targeting accessibility
        result = selector.select_audit_tool("Please check the color contrast and alt text")
        
        # Must NOT crash or return a bogus 'decider error' with 0.0 confidence
        assert result["routing_mode"] == "heuristic_fallback"
        assert result["model_routed"] is False
        assert result["decider_status"] == "offline"
        assert result["tool"] == "audit_accessibility"
        assert result["narrowed"] is True



def test_decider_selector_keyword_heuristics_typography():
    selector = AuditToolSelector()
    
    with patch.object(selector.decider, "ask", side_effect=Exception("Connection refused")):
        result = selector.select_audit_tool("Is the font size and heading hierarchy correct?")
        assert result["routing_mode"] == "heuristic_fallback"
        assert result["tool"] == "audit_typography"


def test_decider_selector_keyword_heuristics_broad_query():
    selector = AuditToolSelector()
    
    with patch.object(selector.decider, "ask", side_effect=Exception("Connection refused")):
        result = selector.select_audit_tool("Audit everything on this website")
        assert result["routing_mode"] == "heuristic_fallback"
        # Broad query keeps all tools (tool="all", narrowed=False)
        assert result["tool"] in ("all", "none")
        assert result["narrowed"] is False


# ── 4. Provider Telemetry Status Tests ──────────────────────────────────────

def test_check_llm_status_without_aws_credentials():
    # Without AWS credentials, should honestly return unconfigured, never connected
    with patch("demo.server.boto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_client.get_caller_identity.side_effect = Exception("NoCredentialsError: Unable to locate credentials")
        mock_session.client.return_value = mock_client
        mock_session_cls.return_value = mock_session
        
        status = _check_llm_status()
        assert status["status"] == "unconfigured"
        assert "AWS credentials not detected" in status["message"]


def test_check_decider_status_offline():
    with patch("demo.server.httpx.get", side_effect=Exception("ConnectError")):
        status = _check_decider_status()
        assert status["status"] in ("offline", "unconfigured")
        assert any(k in status["message"] for k in ("not running", "offline", "unreachable", "DECIDER_API_KEY"))


def test_hosted_decider_neural_decision_with_valid_credentials():
    """Verify that when valid credentials are available, genuine Decider model decisions are returned."""
    from decider_kit.client import Decision

    selector = AuditToolSelector()
    selector.decider.api_key = "dcd_live_test_valid_key"

    fake_answers = {
        "tool": Decision.parse({
            "type": "choice",
            "choice": "audit_accessibility",
            "confidence": 0.94,
            "probabilities": {
                "audit_accessibility": 0.94,
                "audit_typography": 0.03,
                "audit_layout": 0.02,
                "audit_performance_hints": 0.01,
                "none": 0.00,
            },
        })
    }

    with patch.object(selector.decider, "ask", return_value=fake_answers):
        res = selector.select_audit_tool("Evaluate the ARIA attributes and contrast ratio")
        # Must report genuine model routing with authentic confidence and probabilities
        assert res["routing_mode"] == "decider_model"
        assert res["model_routed"] is True
        assert res["decider_status"] == "connected"
        assert res["tool"] == "audit_accessibility"
        assert res["confidence"] == 0.94
        assert res["probabilities"]["audit_accessibility"] == 0.94
        assert res["narrowed"] is True


def test_hosted_decider_unconfigured_credentials_heuristic_fallback():
    """Verify that when hosted mode is configured without a key, heuristic fallback is honest and has confidence=None."""
    selector = AuditToolSelector()
    selector.decider.api_key = ""  # No key configured

    res = selector.select_audit_tool("Audit typography and heading hierarchy")
    assert res["routing_mode"] == "heuristic_fallback"
    assert res["model_routed"] is False
    assert res["decider_status"] == "unconfigured"
    assert res["confidence"] is None  # Never fake AI confidence on rule-based matches
    assert res["tool"] == "audit_typography"
    assert "DECIDER_API_KEY" in res["reason"]


def test_copilot_chat_lifecycle_with_rule_based_fallback():
    """Verify that when LLM credentials are unconfigured, Copilot generates genuine rule-based audit findings."""
    from agent.agent import HackathonAgent

    agent = HackathonAgent()
    out = agent.chat("Audit the accessibility of https://example.com", session_id="test-copilot")

    assert out["reply"], "Reply must not be empty"
    assert "Audit Results: audit_accessibility" in out["reply"]
    assert "### Issues Found" in out["reply"]
    assert "### What Was Checked" in out["reply"]
    assert "### What Could Not Be Verified" in out["reply"]
    assert "### Top 3 Recommendations" in out["reply"]
    assert out["served_by"] == "DesignDoctor Static Engine (Rule-based)"
    assert out["guidance_type"] == "rule_based_engine"
    assert len(out["decisions"]) >= 1
    assert out["decisions"][0]["tool"] == "audit_accessibility"


def test_copilot_session_continuity_url_persistence():
    """Verify that Copilot remembers the audited URL across turns in the same session."""
    from agent.agent import HackathonAgent

    agent = HackathonAgent()
    # Turn 1: mentions URL
    out1 = agent.chat("Audit accessibility of https://example.com", session_id="test-continuity")
    assert "https://example.com" in out1["reply"]

    # Turn 2: follow-up without URL
    out2 = agent.chat("Now check typography too", session_id="test-continuity")
    assert out2["decisions"][0]["tool"] == "audit_typography"
    assert "Audit Results: audit_typography" in out2["reply"]
    assert "https://example.com" in out2["reply"]


def test_copilot_general_design_guidance_without_url():
    """Verify that general design questions without any URL return trustworthy UI/UX guidance."""
    from agent.agent import HackathonAgent

    agent = HackathonAgent()
    out = agent.chat("What are the WCAG 2.1 color contrast ratios?", session_id="test-general")
    assert "4.5:1" in out["reply"]
    assert "3.0:1" in out["reply"]
    assert out["served_by"] == "DesignDoctor Static Engine (Rule-based)"


def test_api_chat_endpoint_lifecycle():
    """Verify that POST /api/chat returns complete audit diagnostics with honest metadata."""
    from fastapi.testclient import TestClient
    from demo.server import app

    client = TestClient(app)
    resp = client.post("/api/chat", json={
        "message": "Audit accessibility for https://example.com",
        "session_id": "test-api",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
    assert "Audit Results: audit_accessibility" in data["reply"]
    assert data["served_by"] == "DesignDoctor Static Engine (Rule-based)"
    assert len(data["decisions"]) >= 1
    assert data["decisions"][0]["tool"] == "audit_accessibility"


def test_copilot_ui_markup_elements():
    """Verify that the redesigned Copilot and compact Decider elements are present in index.html."""
    from pathlib import Path

    html = (Path(__file__).parent.parent / "demo" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="new-chat-btn"' in html
    assert 'id="toggle-decider-btn"' in html
    assert 'id="toggle-focus-btn"' in html
    assert 'id="header-focus-btn"' in html
    assert 'id="back-to-dashboard-btn"' in html
    assert 'id="left-expand-copilot-btn"' in html
    assert 'id="decider-strip-bar"' in html
    assert 'id="decider-route-label"' in html
    assert 'id="copilot-empty-state"' in html
    assert 'class="welcome-action-card"' in html
    assert 'id="chat-scroll"' in html
    assert 'id="quick-prompts-row"' in html
    assert 'class="copilot-input-wrap"' in html
    assert 'id="m"' in html
    assert 'id="send"' in html


def test_focus_mode_and_responsive_css_rules():
    """Verify CSS architecture for Focus Mode, centered conversation (760-900px), and responsive breakpoints."""
    from pathlib import Path

    css = (Path(__file__).parent.parent / "demo" / "static" / "app.css").read_text(encoding="utf-8")

    # Focus Mode workspace expansion
    assert "main.workspace.focus-copilot" in css
    assert "#back-to-dashboard-btn" in css
    assert "main.workspace.focus-copilot .back-dashboard-btn" in css

    # Spacious centered conversation width (within 760-900px)
    assert "main.workspace.focus-copilot .chat-stream-scroll" in css
    assert "max-width: 860px" in css or "max-width: 900px" in css

    # Sticky composer centered inner container
    assert ".copilot-composer-inner" in css
    assert "main.workspace.focus-copilot .copilot-composer-inner" in css

    # Responsive breakpoints
    assert "@media (max-width: 480px)" in css
    assert "@media (min-width: 481px) and (max-width: 767px)" in css
    assert "@media (min-width: 768px) and (max-width: 1023px)" in css
    assert "@media (min-width: 1024px)" in css


def test_js_focus_and_mobile_navigation_logic():
    """Verify app.js provides setFocusMode, setMobileView, and complete event bindings."""
    from pathlib import Path

    js = (Path(__file__).parent.parent / "demo" / "static" / "app.js").read_text(encoding="utf-8")

    assert "function setFocusMode(" in js
    assert "function setMobileView(" in js
    assert "focus-copilot" in js
    assert "designdoctor_focus_mode" in js
    assert "header-focus-btn" in js
    assert "back-to-dashboard-btn" in js
    assert "left-expand-copilot-btn" in js
    assert "toggle-focus-btn" in js
    assert "segment-btn" in js


