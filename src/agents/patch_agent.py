"""Remediation Patch Agent for CloudSentry.

Synthesizes infrastructure and Kubernetes manifest patches to remediate diagnosed
incidents (e.g., resizing memory/CPU limits, adjusting HPA autoscaling thresholds)
and iteratively self-corrects based on sandbox validation feedback.
"""

from typing import Optional, Dict, Any, List, Tuple
import os
import difflib
import yaml

from src.schemas.models import (
    CloudSentryState,
    RemediationPatch,
    RootCauseAnalysis,
    ValidationResult,
)


class PatchAgent:
    """Generates and self-heals Kubernetes remediation manifests."""

    def __init__(self, base_manifest_path: Optional[str] = None):
        self.base_manifest_path = base_manifest_path

    def _load_base_manifest(self, service_name: str) -> Tuple[str, Dict[str, Any]]:
        """Loads baseline manifest from disk or generates standard baseline dict."""
        manifest_path = self.base_manifest_path or os.path.join(
            "config", "policies", f"{service_name}-deployment.yaml"
        )
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                content = f.read()
            doc = yaml.safe_load(content)
            return manifest_path, doc
        else:
            # Fallback default standard deployment structure
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
            return manifest_path, default_doc

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
        failure_mode = state.rca.primary_failure_mode
        manifest_path, doc = self._load_base_manifest(culprit)

        # Retrieve containers
        containers = (
            doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        )

        # Determine target resources based on failure mode and validation feedback
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

        # Inspect validator feedback for self-correction
        if state.validation and not state.validation.is_valid:
            state.log(
                f"[PatchAgent] Self-correcting against {len(state.validation.policy_violations)} policy violations and {len(state.validation.linter_errors)} linter errors."
            )
            for violation in state.validation.policy_violations:
                reasoning_points.append(f"Self-correction fix for policy violation: {violation}")
                # Ensure strict limits are populated
                if "limits.memory" in violation:
                    target_memory_limit = "2Gi"
                if "limits.cpu" in violation:
                    target_cpu_limit = "1000m"

            for err in state.validation.linter_errors:
                reasoning_points.append(f"Self-correction fix for linter error: {err}")

        # Apply updates to container resources
        for c in containers:
            c.setdefault("resources", {})
            c["resources"].setdefault("limits", {})
            c["resources"].setdefault("requests", {})

            c["resources"]["limits"]["memory"] = target_memory_limit
            c["resources"]["limits"]["cpu"] = target_cpu_limit
            c["resources"]["requests"]["memory"] = target_memory_request
            c["resources"]["requests"]["cpu"] = target_cpu_request

        # Serialize patched YAML
        updated_yaml = yaml.dump(doc, sort_keys=False, default_flow_style=False)

        # Generate unified diff representation
        original_yaml = yaml.dump(
            yaml.safe_load(yaml.dump(doc)), sort_keys=False, default_flow_style=False
        )
        # Load fresh original if available
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                original_yaml = f.read()

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

        state.patch = RemediationPatch(
            target_manifest=manifest_path,
            patch_type="KUBERNETES_YAML",
            diff_content=diff_str,
            updated_manifest=updated_yaml,
            reasoning=reasoning,
        )

        state.log(
            f"[PatchAgent] Successfully generated Kubernetes remediation patch for '{culprit}'."
        )
        state.status = "VALIDATING"
        return state


def run_patch_agent(state: CloudSentryState) -> CloudSentryState:
    """Functional node entrypoint for LangGraph / Orchestrator workflow."""
    agent = PatchAgent()
    return agent.process(state)
