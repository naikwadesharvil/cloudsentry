"""Unit and integration tests for LLM structured reasoning and deterministic fallbacks.
"""

from unittest.mock import MagicMock, patch
import pytest
import os
import yaml
from pydantic import ValidationError

from src.schemas.models import (
    RootCauseAnalysis,
    RemediationPatch,
    CloudSentryState,
    ValidationResult,
)
from src.tools.metric_generator import generate_incident_telemetry
from src.tools.anomaly_detector import detect_anomalies
from src.tools.llm_provider import is_llm_available, get_chat_model, invoke_structured_llm
from src.agents.telemetry_agent import run_telemetry_agent
from src.agents.rca_agent import RCAAgent, run_rca_agent
from src.agents.patch_agent import PatchAgent, run_patch_agent
from src.agents.validator_agent import run_validator_agent
from src.agents.orchestrator import CloudSentryOrchestrator


def test_schema_contracts():
    """Verifies strict schema contracts for RootCauseAnalysis and RemediationPatch."""
    # 1. Valid RCA
    rca = RootCauseAnalysis(
        culprit_service="checkout-service",
        primary_failure_mode="OOM_KILL",
        evidence_logs=["Memory leak detected (+140% growth)"],
        confidence_score=0.95,
    )
    assert rca.culprit_service == "checkout-service"
    assert rca.primary_failure_mode == "OOM_KILL"
    assert rca.confidence_score == 0.95

    # Invalid failure mode must fail Pydantic validation
    with pytest.raises(ValidationError):
        RootCauseAnalysis(
            culprit_service="checkout-service",
            primary_failure_mode="INVALID_MODE",  # type: ignore
            evidence_logs=[],
            confidence_score=0.5,
        )

    # 2. Valid RemediationPatch
    patch_obj = RemediationPatch(
        target_manifest="config/policies/checkout-service-deployment.yaml",
        patch_type="KUBERNETES_YAML",
        diff_content="+ memory: 2Gi",
        reasoning="Resized memory limit",
    )
    assert patch_obj.patch_type == "KUBERNETES_YAML"

    with pytest.raises(ValidationError):
        RemediationPatch(
            target_manifest="config/policies/checkout-service-deployment.yaml",
            patch_type="ANSIBLE",  # type: ignore
            diff_content="",
            reasoning="",
        )


def test_offline_deterministic_fallback(monkeypatch):
    """Ensures RCA and Patch agents function flawlessly when no LLM API keys are present."""
    # Clear all potential API keys
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    assert is_llm_available() is False
    assert get_chat_model() is None

    telemetry = generate_incident_telemetry(num_steps=20)
    state = CloudSentryState(metrics=telemetry)
    state = run_telemetry_agent(state)

    # 1. Test RCAAgent offline fallback
    rca_agent = RCAAgent(enable_llm=True)
    state = rca_agent.process(state)

    assert state.rca is not None
    assert state.rca.culprit_service == "checkout-service"
    assert state.rca.primary_failure_mode == "OOM_KILL"
    assert state.rca.confidence_score >= 0.8
    assert any("deterministic" in log.lower() for log in state.history_logs)

    # 2. Test PatchAgent offline fallback
    patch_agent = PatchAgent(enable_llm=True)
    state = patch_agent.process(state)

    assert state.patch is not None
    assert state.patch.patch_type == "KUBERNETES_YAML"
    assert state.patch.updated_manifest is not None
    assert "2Gi" in state.patch.updated_manifest
    assert any("deterministic" in log.lower() for log in state.history_logs)


def test_llm_structured_mocking_success():
    """Tests that RCAAgent and PatchAgent seamlessly adopt structured output from LLMs."""
    telemetry = generate_incident_telemetry(num_steps=20)
    state = CloudSentryState(metrics=telemetry)
    state = run_telemetry_agent(state)

    mock_rca = RootCauseAnalysis(
        culprit_service="checkout-service",
        primary_failure_mode="OOM_KILL",
        evidence_logs=["LLM-diagnosed linear memory escalation exceeding container cgroup limits."],
        confidence_score=0.99,
    )

    with patch("src.agents.rca_agent.invoke_structured_llm", return_value=mock_rca):
        rca_agent = RCAAgent(enable_llm=True)
        state = rca_agent.process(state)

        assert state.rca is not None
        assert state.rca.confidence_score == 0.99
        assert "LLM reasoning completed" in " ".join(state.history_logs)

    mock_patch = RemediationPatch(
        target_manifest="config/policies/checkout-service-deployment.yaml",
        patch_type="KUBERNETES_YAML",
        diff_content="--- a/deploy.yaml\n+++ b/deploy.yaml\n@@ -20,2 +20,2 @@\n- memory: 512Mi\n+ memory: 2Gi",
        updated_manifest="""apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-service
spec:
  template:
    spec:
      containers:
        - name: checkout-api
          resources:
            limits:
              memory: "2Gi"
              cpu: "1000m"
""",
        reasoning="LLM synthesized FinOps compliant patch with 2Gi memory headroom.",
    )

    with patch("src.agents.patch_agent.invoke_structured_llm", return_value=mock_patch):
        patch_agent = PatchAgent(enable_llm=True)
        state = patch_agent.process(state)

        assert state.patch is not None
        assert "LLM synthesized FinOps compliant patch" in state.patch.reasoning
        assert "LLM generated valid Kubernetes patch" in " ".join(state.history_logs)


def test_llm_exception_fallback_handling():
    """Tests that LLM exceptions (e.g. RateLimitError, Timeout) trigger graceful heuristic fallback."""
    telemetry = generate_incident_telemetry(num_steps=20)
    state = CloudSentryState(metrics=telemetry)
    state = run_telemetry_agent(state)

    # Force invoke_structured_llm to raise an exception
    with patch(
        "src.agents.rca_agent.invoke_structured_llm",
        side_effect=RuntimeError("Groq / Gemini 429 ResourceExhausted: rate limit reached"),
    ):
        rca_agent = RCAAgent(enable_llm=True)
        state = rca_agent.process(state)

        # Must not crash! Deterministic fallback should kick in
        assert state.rca is not None
        assert state.rca.culprit_service == "checkout-service"
        assert state.rca.primary_failure_mode == "OOM_KILL"
        assert any("fallback" in log.lower() or "exception" in log.lower() for log in state.history_logs)

    with patch(
        "src.agents.patch_agent.invoke_structured_llm",
        side_effect=TimeoutError("LLM inference timed out after 30000ms"),
    ):
        patch_agent = PatchAgent(enable_llm=True)
        state = patch_agent.process(state)

        assert state.patch is not None
        assert state.patch.updated_manifest is not None
        assert "2Gi" in state.patch.updated_manifest
        assert any("fallback" in log.lower() or "exception" in log.lower() for log in state.history_logs)


def test_full_orchestrator_end_to_end_offline():
    """Runs complete end-to-end multi-agent pipeline verifying offline remediation success."""
    telemetry = generate_incident_telemetry(num_steps=20)
    orchestrator = CloudSentryOrchestrator(use_langgraph=True)

    final_state = orchestrator.run(telemetry)

    assert final_state.status == "REMEDIATED"
    assert final_state.rca is not None
    assert final_state.rca.culprit_service == "checkout-service"
    assert final_state.patch is not None
    assert final_state.validation is not None
    assert final_state.validation.is_valid is True
