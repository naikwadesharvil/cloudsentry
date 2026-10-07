"""End-to-end and modular test suite for CloudSentry autonomous remediation.
"""

import pytest
import yaml
from src.schemas.models import (
    MetricPoint,
    CloudSentryState,
    RemediationPatch,
    ValidationResult,
)
from src.tools.metric_generator import MetricGenerator, generate_incident_telemetry
from src.tools.anomaly_detector import MetricAnomalyDetector, detect_anomalies
from src.tools.k8s_sandbox import KubernetesSandboxValidator, validate_k8s_manifest
from src.agents.telemetry_agent import TelemetryAgent, run_telemetry_agent
from src.agents.rca_agent import RCAAgent, run_rca_agent
from src.agents.patch_agent import PatchAgent, run_patch_agent
from src.agents.validator_agent import ValidatorAgent, run_validator_agent
from src.agents.orchestrator import CloudSentryOrchestrator, run_incident_remediation


def test_metric_generator():
    """Validates synthetic telemetry generation for degraded and healthy microservices."""
    gen = MetricGenerator(random_seed=42)
    metrics = gen.generate_cluster_telemetry(
        culprit_service="checkout-service",
        culprit_scenario="OOM_KILL",
        num_steps=20,
    )
    assert len(metrics) > 0
    services = {m.service_name for m in metrics}
    assert "checkout-service" in services
    assert "auth-service" in services

    checkout_metrics = [m for m in metrics if m.service_name == "checkout-service"]
    assert len(checkout_metrics) == 20
    # Memory should be growing significantly
    assert checkout_metrics[-1].memory_usage_mb > checkout_metrics[0].memory_usage_mb * 2


def test_anomaly_detection():
    """Asserts that anomaly detector flags degraded checkout-service and passes healthy peers."""
    telemetry = generate_incident_telemetry(num_steps=20)
    reports = detect_anomalies(telemetry)

    report_map = {r.service_name: r for r in reports}
    assert "checkout-service" in report_map
    assert report_map["checkout-service"].anomaly_detected is True
    assert report_map["checkout-service"].severity in ["HIGH", "CRITICAL"]
    assert "memory" in (report_map["checkout-service"].trigger_metric or "")

    # Healthy peer services should not flag high/critical anomalies
    if "auth-service" in report_map:
        assert report_map["auth-service"].severity in ["LOW", "MEDIUM"]


def test_k8s_sandbox_validator_policy_rules():
    """Validates deterministic k8s sandbox enforcement of resource limits."""
    validator = KubernetesSandboxValidator()

    # 1. Invalid YAML: missing resource limits
    invalid_manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vulnerable-app
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vulnerable-app
  template:
    metadata:
      labels:
        app: vulnerable-app
    spec:
      containers:
        - name: app
          image: nginx:latest
"""
    res = validator.validate_manifest(invalid_manifest)
    assert res.is_valid is False
    assert any("limits" in v for v in res.policy_violations)

    # 2. Invalid YAML: unbounded resource limits
    unbounded_manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: unbounded-app
spec:
  replicas: 1
  selector:
    matchLabels:
      app: unbounded-app
  template:
    metadata:
      labels:
        app: unbounded-app
    spec:
      containers:
        - name: app
          image: nginx:latest
          resources:
            limits:
              memory: "unbounded"
              cpu: "none"
"""
    res_unbounded = validator.validate_manifest(unbounded_manifest)
    assert res_unbounded.is_valid is False
    assert len(res_unbounded.policy_violations) > 0

    # 3. Valid YAML: properly specified resources
    valid_manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: secure-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: secure-app
  template:
    metadata:
      labels:
        app: secure-app
    spec:
      containers:
        - name: app
          image: nginx:latest
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "1000m"
"""
    res_valid = validator.validate_manifest(valid_manifest)
    assert res_valid.is_valid is True
    assert len(res_valid.linter_errors) == 0
    assert len(res_valid.policy_violations) == 0


def test_rca_agent_diagnosis():
    """Validates RCA agent correlates metrics to correctly classify OOM_KILL failure mode."""
    telemetry = generate_incident_telemetry(num_steps=20)
    state = CloudSentryState(metrics=telemetry)

    state = run_telemetry_agent(state)
    state = run_rca_agent(state)

    assert state.rca is not None
    assert state.rca.culprit_service == "checkout-service"
    assert state.rca.primary_failure_mode == "OOM_KILL"
    assert state.rca.confidence_score >= 0.8
    assert len(state.rca.evidence_logs) > 0


def test_end_to_end_remediation_pipeline():
    """End-to-end integration test verifying the entire agentic loop.

    Asserts:
    1. Anomaly is detected in the telemetry stream.
    2. The culprit service (checkout-service) is correctly identified.
    3. A valid Kubernetes YAML patch is synthesized and passes the policy validator.
    4. Master state reaches REMEDIATED status.
    """
    telemetry = generate_incident_telemetry(num_steps=20)
    assert len(telemetry) > 0

    # Run orchestrator
    final_state = run_incident_remediation(telemetry)

    # 1. Anomaly detected
    assert len(final_state.anomalies) > 0
    flagged = [a for a in final_state.anomalies if a.anomaly_detected]
    assert len(flagged) >= 1
    assert any(a.service_name == "checkout-service" for a in flagged)

    # 2. Culprit correctly identified
    assert final_state.rca is not None
    assert final_state.rca.culprit_service == "checkout-service"
    assert final_state.rca.primary_failure_mode == "OOM_KILL"

    # 3. Valid Kubernetes YAML patch synthesized and validated
    assert final_state.patch is not None
    assert final_state.patch.patch_type == "KUBERNETES_YAML"
    assert "checkout-service" in final_state.patch.target_manifest
    assert len(final_state.patch.diff_content) > 0

    # Parse and check the updated manifest
    assert final_state.patch.updated_manifest is not None
    parsed_yaml = yaml.safe_load(final_state.patch.updated_manifest)
    assert parsed_yaml["kind"] == "Deployment"
    assert parsed_yaml["metadata"]["name"] == "checkout-service"

    container = parsed_yaml["spec"]["template"]["spec"]["containers"][0]
    assert "resources" in container
    assert "limits" in container["resources"]
    assert container["resources"]["limits"]["memory"] == "2Gi"
    assert container["resources"]["limits"]["cpu"] == "1000m"

    # 4. Sandbox validation passed
    assert final_state.validation is not None
    assert final_state.validation.is_valid is True
    assert len(final_state.validation.linter_errors) == 0
    assert len(final_state.validation.policy_violations) == 0
    assert final_state.status == "REMEDIATED"


def test_agent_self_correction_loop():
    """Tests the agent's ability to self-heal when presented with policy feedback."""
    validator = KubernetesSandboxValidator()
    patch_agent = PatchAgent()

    # Simulate an invalid state with a policy violation (e.g. missing limits)
    state = CloudSentryState(
        metrics=generate_incident_telemetry(num_steps=20),
        status="VALIDATING",
    )
    state = run_telemetry_agent(state)
    state = run_rca_agent(state)

    # Seed an invalid validation result
    state.validation = ValidationResult(
        is_valid=False,
        policy_violations=["Container 'checkout-api' missing strict 'resources.limits.memory'."],
        linter_errors=[],
        retry_count=1,
    )

    # Trigger patch agent to self-correct
    state = patch_agent.process(state)
    assert state.patch is not None
    assert "Self-correction fix" in state.patch.reasoning

    # Validate the repaired patch
    val_res = validator.validate_patch(state.patch)
    assert val_res.is_valid is True
