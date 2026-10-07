"""Deterministic Kubernetes YAML linter and policy validation sandbox.

Verifies schema compliance, structural integrity, and FinOps/Security resource limits
(e.g., preventing unbounded memory/CPU allocations).
"""

from typing import List, Dict, Any, Optional, Tuple
import re
import yaml

from src.schemas.models import ValidationResult, RemediationPatch


class KubernetesSandboxValidator:
    """Validates Kubernetes manifests against structural schemas and FinOps guardrails."""

    MEMORY_REGEX = re.compile(r"^([0-9]+(\.[0-9]+)?)(E|P|T|G|M|k|Ei|Pi|Ti|Gi|Mi|Ki|m)?$")
    CPU_REGEX = re.compile(r"^([0-9]+(\.[0-9]+)?m?)$")
    PROHIBITED_VALUES = {"unbounded", "infinite", "none", "null", "0", "unlimited", "*"}

    def __init__(self, max_memory_mb: int = 32768, max_cpu_cores: float = 16.0):
        self.max_memory_mb = max_memory_mb
        self.max_cpu_cores = max_cpu_cores

    def validate_manifest(self, manifest_content: str, retry_count: int = 0) -> ValidationResult:
        """Parses and runs complete validation against a Kubernetes YAML manifest string."""
        linter_errors: List[str] = []
        policy_violations: List[str] = []

        # 1. YAML Syntax Parsing
        if not manifest_content or not manifest_content.strip():
            return ValidationResult(
                is_valid=False,
                linter_errors=["Manifest content is empty or blank."],
                policy_violations=[],
                retry_count=retry_count,
            )

        try:
            documents = list(yaml.safe_load_all(manifest_content))
        except yaml.YAMLError as exc:
            return ValidationResult(
                is_valid=False,
                linter_errors=[f"YAML parsing error: {str(exc)}"],
                policy_violations=[],
                retry_count=retry_count,
            )

        if not documents or documents[0] is None:
            return ValidationResult(
                is_valid=False,
                linter_errors=["Parsed YAML contains no valid documents or is None."],
                policy_violations=[],
                retry_count=retry_count,
            )

        # 2. Schema and Field Checks
        for idx, doc in enumerate(documents):
            if not isinstance(doc, dict):
                linter_errors.append(f"Document {idx} is not a valid YAML mapping/object.")
                continue

            # Core Top-Level K8s Fields
            for field in ["apiVersion", "kind", "metadata"]:
                if field not in doc:
                    linter_errors.append(f"Document {idx} missing required top-level field: '{field}'")

            metadata = doc.get("metadata", {})
            if isinstance(metadata, dict):
                if "name" not in metadata:
                    linter_errors.append(f"Document {idx} metadata missing 'name'")
            else:
                linter_errors.append(f"Document {idx} 'metadata' must be a mapping.")

            kind = doc.get("kind", "")
            spec = doc.get("spec", {})

            # 3. Workload Container Resources Validation
            if kind in ["Deployment", "StatefulSet", "DaemonSet", "Job", "Pod"]:
                containers: List[Dict[str, Any]] = []

                if kind == "Pod":
                    containers = spec.get("containers", []) if isinstance(spec, dict) else []
                else:
                    template_spec = spec.get("template", {}).get("spec", {}) if isinstance(spec, dict) else {}
                    containers = template_spec.get("containers", []) if isinstance(template_spec, dict) else []

                if not containers or not isinstance(containers, list):
                    linter_errors.append(f"Workload {kind} has no containers defined under spec.")
                    continue

                for c_idx, container in enumerate(containers):
                    c_name = container.get("name", f"container-{c_idx}")
                    resources = container.get("resources", {})

                    if not resources or not isinstance(resources, dict):
                        policy_violations.append(
                            f"Container '{c_name}' in {kind} is missing 'resources' configuration and 'resources.limits' (Unbounded Resource Risk)."
                        )
                        continue

                    limits = resources.get("limits", {})
                    if not limits or not isinstance(limits, dict):
                        policy_violations.append(
                            f"Container '{c_name}' in {kind} has NO 'resources.limits' defined (Unbounded Resource Risk)."
                        )
                        continue

                    # Validate memory limit
                    mem_limit = str(limits.get("memory", "")).strip()
                    if not mem_limit:
                        policy_violations.append(
                            f"Container '{c_name}' missing strict 'resources.limits.memory'."
                        )
                    elif mem_limit.lower() in self.PROHIBITED_VALUES:
                        policy_violations.append(
                            f"Container '{c_name}' has illegal/unbounded memory limit '{mem_limit}'."
                        )
                    elif not self.MEMORY_REGEX.match(mem_limit):
                        linter_errors.append(
                            f"Container '{c_name}' memory limit '{mem_limit}' is not a valid Kubernetes quantity (e.g., 512Mi, 2Gi)."
                        )

                    # Validate CPU limit
                    cpu_limit = str(limits.get("cpu", "")).strip()
                    if not cpu_limit:
                        policy_violations.append(
                            f"Container '{c_name}' missing strict 'resources.limits.cpu'."
                        )
                    elif cpu_limit.lower() in self.PROHIBITED_VALUES:
                        policy_violations.append(
                            f"Container '{c_name}' has illegal/unbounded CPU limit '{cpu_limit}'."
                        )
                    elif not self.CPU_REGEX.match(cpu_limit):
                        linter_errors.append(
                            f"Container '{c_name}' CPU limit '{cpu_limit}' is not a valid Kubernetes quantity (e.g., 500m, 2)."
                        )

                    # Check requests vs limits if requests exist
                    requests = resources.get("requests", {})
                    if isinstance(requests, dict):
                        req_mem = str(requests.get("memory", "")).strip()
                        req_cpu = str(requests.get("cpu", "")).strip()
                        if req_mem and req_mem.lower() in self.PROHIBITED_VALUES:
                            policy_violations.append(
                                f"Container '{c_name}' has illegal memory request '{req_mem}'."
                            )
                        if req_cpu and req_cpu.lower() in self.PROHIBITED_VALUES:
                            policy_violations.append(
                                f"Container '{c_name}' has illegal CPU request '{req_cpu}'."
                            )

        is_valid = len(linter_errors) == 0 and len(policy_violations) == 0

        return ValidationResult(
            is_valid=is_valid,
            linter_errors=linter_errors,
            policy_violations=policy_violations,
            retry_count=retry_count,
        )

    def validate_patch(self, patch: RemediationPatch, retry_count: int = 0) -> ValidationResult:
        """Validates the target manifest content of a RemediationPatch candidate."""
        content = patch.updated_manifest or patch.diff_content
        return self.validate_manifest(content, retry_count=retry_count)


def validate_k8s_manifest(manifest_content: str, retry_count: int = 0) -> ValidationResult:
    """Convenience helper function to validate a Kubernetes YAML manifest."""
    sandbox = KubernetesSandboxValidator()
    return sandbox.validate_manifest(manifest_content, retry_count=retry_count)
