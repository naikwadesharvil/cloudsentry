"""Validator Agent for CloudSentry.

Executes deterministic policy validation and syntax linting on proposed remediation
patches. Dictates whether the patch is sound or if self-correction iterations are required.
"""

from typing import Optional
from src.schemas.models import CloudSentryState, ValidationResult
from src.tools.k8s_sandbox import KubernetesSandboxValidator


class ValidatorAgent:
    """Agent responsible for deterministic sandbox validation and retry loop control."""

    def __init__(self, validator: Optional[KubernetesSandboxValidator] = None, max_retries: int = 3):
        self.validator = validator or KubernetesSandboxValidator()
        self.max_retries = max_retries

    def process(self, state: CloudSentryState) -> CloudSentryState:
        """Validates current remediation patch and decides if remediation succeeds or repeats."""
        state.log(f"[ValidatorAgent] Inspecting proposed patch in sandbox environment.")

        if not state.patch:
            state.log("[ValidatorAgent] Error: No patch available to validate.")
            state.validation = ValidationResult(
                is_valid=False,
                linter_errors=["No patch provided in system state."],
                policy_violations=[],
                retry_count=state.iteration_count,
            )
            state.status = "FAILED"
            return state

        current_retries = state.validation.retry_count if state.validation else 0
        validation_res = self.validator.validate_patch(state.patch, retry_count=current_retries)

        if validation_res.is_valid:
            state.validation = validation_res
            state.status = "REMEDIATED"
            state.log(
                "[ValidatorAgent] Validation PASSED. Patch satisfies all FinOps & Security policies."
            )
        else:
            validation_res.retry_count += 1
            state.validation = validation_res

            if validation_res.retry_count > self.max_retries:
                state.status = "FAILED"
                state.log(
                    f"[ValidatorAgent] Validation FAILED after {validation_res.retry_count} attempts. Max retries exceeded."
                )
            else:
                state.status = "PATCHING"  # Route back to patch agent for self-correction
                state.log(
                    f"[ValidatorAgent] Validation FAILED (Attempt {validation_res.retry_count}/{self.max_retries}). Requesting self-correction from PatchAgent. Violations: {validation_res.policy_violations + validation_res.linter_errors}"
                )

        return state


def run_validator_agent(state: CloudSentryState) -> CloudSentryState:
    """Functional node entrypoint for LangGraph / Orchestrator workflow."""
    agent = ValidatorAgent()
    return agent.process(state)
