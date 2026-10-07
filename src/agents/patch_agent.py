"""Remediation Patch Agent for CloudSentry.

Synthesizes infrastructure and Kubernetes manifest patches to remediate diagnosed
incidents (e.g., resizing memory/CPU limits, adjusting HPA autoscaling thresholds)
using LLM structured reasoning with automatic deterministic offline fallback.
"""

from typing import Optional, Dict, Any, List, Tuple
import os
import difflib
import json
import yaml

from src.schemas.models import (
    CloudSentryState,
    RemediationPatch,
    RootCauseAnalysis,
    ValidationResult,
)
from src.tools.llm_provider import invoke_structured_llm, is_llm_available, get_chat_model


PATCH_SYSTEM_PROMPT = """You are CloudSentry's Kubernetes Patch & FinOps Remediation AI.
Ingest the baseline Kubernetes deployment manifest, the Root Cause Analysis diagnosis, and any sandbox validation failures/linter errors.
Synthesize a fully valid, production-ready Kubernetes YAML manifest and diff that resolves the incident while strictly complying with FinOps & Security policies:
1. Every container MUST have strict 'resources.limits.memory' (e.g. '1Gi', '2Gi') and 'resources.limits.cpu' (e.g. '1000m', '2').
2. Prohibited values: 'unbounded', 'infinite', 'none', 'null', '0', empty.
3. Ensure 'resources.requests' are defined and <= limits.
4. Output must strictly conform to the RemediationPatch schema.
"""


class PatchAgent:
    """Generates and self-heals Kubernetes remediation manifests."""

    def __init__(
        self,
        base_manifest_path: Optional[str] = None,
        chat_model: Optional[Any] = None,
        enable_llm: bool = True,
    ):
        self.base_manifest_path = base_manifest_path
        self.chat_model = chat_model
        self.enable_llm = enable_llm

    def _load_base_manifest(self, service_name: str) -> Tuple[str, Dict[str, Any], str]:
        """Loads baseline manifest from disk or generates standard baseline dict."""
        manifest_path = self.base_manifest_path or os.path.join(
            "config", "policies", f"{service_name}-deployment.yaml"
        )
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                content = f.read()
            doc = yaml.safe_load(content)
            return manifest_path, doc, content
        else:
            default_doc = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": service_name, "namespace": "production"},
                "spec": {
                    "replicas": 3,
                    "selector": {"matchLabels": {"app": service_name}},
                    "template": {
                        "metadata": {"labels": {"app": service_name}},
                        "spec": {
                            "containers": [
                                {
                                    "name": f"{service_name}-api",
                                    "image": f"ghcr.io/org/{service_name}:latest",
                                    "resources": {
                                        "requests": {"memory": "256Mi", "cpu": "200m"},
                                        "limits": {"memory": "512Mi", "cpu": "500m"},
                                    },
                                }
                            ]
                        },
                    },
                },
            }
            content = yaml.dump(default_doc, sort_keys=False, default_flow_style=False)
            return manifest_path, default_doc, content

    def _synthesize_with_llm(
        self, state: CloudSentryState, manifest_path: str, original_yaml: str
    ) -> Optional[RemediationPatch]:
        """Attempts LLM-powered structured patch synthesis."""
        if not self.enable_llm and self.chat_model is None:
            return None

        validation_info = ""
        if state.validation and not state.validation.is_valid:
            validation_info = f"""
Previous Sandbox Validation Feedback:
- Policy Violations: {json.dumps(state.validation.policy_violations)}
- Linter Errors: {json.dumps(state.validation.linter_errors)}
- Attempt: {state.validation.retry_count}
"""

        user_prompt = f"""Target Manifest Path: {manifest_path}
Root Cause Analysis Diagnosis:
- Culprit Service: {state.rca.culprit_service}
- Failure Mode: {state.rca.primary_failure_mode}
- Evidence: {json.dumps(state.rca.evidence_logs)}
- Confidence: {state.rca.confidence_score}
{validation_info}

Original Kubernetes YAML:
```yaml
{original_yaml}
```

Generate the remediation patch with updated_manifest, diff_content, and reasoning.
"""
        patch_res = invoke_structured_llm(
            schema=RemediationPatch,
            system_prompt=PATCH_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=self.chat_model,
        )

        if patch_res and patch_res.updated_manifest:
            # Validate YAML syntax sanity
            try:
                yaml.safe_load(patch_res.updated_manifest)
                return patch_res
            except Exception:
                return None

        return None

    def _synthesize_deterministic(
        self,
        state: CloudSentryState,
        manifest_path: str,
        doc: Dict[str, Any],
        original_yaml: str,
    ) -> RemediationPatch:
        """Deterministic heuristic patch synthesis engine."""
        culprit = state.rca.culprit_service if state.rca else "service"
        failure_mode = state.rca.primary_failure_mode if state.rca else "OOM_KILL"

        containers = (
            doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        )

        target_memory_limit = "2Gi"
        target_cpu_limit = "1000m"
        target_memory_request = "512Mi"
        target_cpu_request = "500m"
        reasoning_points: List[str] = []

        if failure_mode == "OOM_KILL":
            target_memory_limit = "2Gi"
            target_memory_request = "1Gi"
            target_cpu_limit = "1000m"
            target_cpu_request = "500m"
            reasoning_points.append(
                f"Resized container memory limit from 512Mi to {target_memory_limit} and request to {target_memory_request} to prevent Out-Of-Memory termination during traffic bursts."
            )
        elif failure_mode == "CPU_THROTTLING":
            target_cpu_limit = "2000m"
            target_cpu_request = "1000m"
            target_memory_limit = "1Gi"
            reasoning_points.append(
                f"Scaled CPU limits to {target_cpu_limit} to eliminate CPU throttling and latency queuing."
            )
        else:  # LATENCY_SPIKE
            target_memory_limit = "1Gi"
            target_cpu_limit = "1500m"
            reasoning_points.append(
                f"Allocated additional compute headroom ({target_cpu_limit} CPU, {target_memory_limit} Memory) to reduce latency bottlenecks."
            )

        if state.validation and not state.validation.is_valid:
            state.log(
                f"[PatchAgent] Self-correcting against {len(state.validation.policy_violations)} policy violations and {len(state.validation.linter_errors)} linter errors."
            )
            for violation in state.validation.policy_violations:
                reasoning_points.append(f"Self-correction fix for policy violation: {violation}")
                if "limits.memory" in violation:
                    target_memory_limit = "2Gi"
                if "limits.cpu" in violation:
                    target_cpu_limit = "1000m"

            for err in state.validation.linter_errors:
                reasoning_points.append(f"Self-correction fix for linter error: {err}")

        for c in containers:
            c.setdefault("resources", {})
            c["resources"].setdefault("limits", {})
            c["resources"].setdefault("requests", {})

            c["resources"]["limits"]["memory"] = target_memory_limit
            c["resources"]["limits"]["cpu"] = target_cpu_limit
            c["resources"]["requests"]["memory"] = target_memory_request
            c["resources"]["requests"]["cpu"] = target_cpu_request

        updated_yaml = yaml.dump(doc, sort_keys=False, default_flow_style=False)

        diff_lines = list(
            difflib.unified_diff(
                original_yaml.splitlines(keepends=True),
                updated_yaml.splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(manifest_path)}",
                tofile=f"b/{os.path.basename(manifest_path)}",
            )
        )
        diff_str = "".join(diff_lines) if diff_lines else "# No diff detected (direct replacement)"
        reasoning = " | ".join(reasoning_points)

        return RemediationPatch(
            target_manifest=manifest_path,
            patch_type="KUBERNETES_YAML",
            diff_content=diff_str,
            updated_manifest=updated_yaml,
            reasoning=reasoning,
        )

    def process(self, state: CloudSentryState) -> CloudSentryState:
        """Synthesizes or refines remediation patch manifest based on RCA and feedback."""
        state.iteration_count += 1
        state.log(
            f"[PatchAgent] Iteration {state.iteration_count}: Synthesizing remediation patch."
        )

        if not state.rca:
            state.log("[PatchAgent] Error: No RCA available to guide remediation.")
            return state

        culprit = state.rca.culprit_service
        manifest_path, doc, original_yaml = self._load_base_manifest(culprit)

        patch_res: Optional[RemediationPatch] = None

        # 1. Attempt LLM patch synthesis if enabled
        if self.enable_llm or self.chat_model is not None:
            try:
                patch_res = self._synthesize_with_llm(state, manifest_path, original_yaml)
                if patch_res:
                    state.log(f"[PatchAgent] LLM generated valid Kubernetes patch for '{culprit}'.")
            except Exception as e:
                state.log(f"[PatchAgent] LLM patch generation exception ({e}); falling back to deterministic builder.")
                patch_res = None

        # 2. Fall back to Deterministic Patch Engine
        if not patch_res:
            state.log("[PatchAgent] Using deterministic patch synthesis engine.")
            patch_res = self._synthesize_deterministic(state, manifest_path, doc, original_yaml)

        state.patch = patch_res
        state.log(
            f"[PatchAgent] Successfully prepared Kubernetes remediation patch for '{culprit}'."
        )
        state.status = "VALIDATING"
        return state


def run_patch_agent(state: CloudSentryState) -> CloudSentryState:
    """Functional node entrypoint for LangGraph / Orchestrator workflow."""
    agent = PatchAgent()
    return agent.process(state)
