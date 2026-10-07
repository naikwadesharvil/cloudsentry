"""Empirical Benchmarking & Quantitative Evaluation Suite for CloudSentry.

Simulates 50+ distributed multi-service failure incidents across diverse topologies,
evaluating Detection Accuracy, Mean Time to Resolution (MTTR), Zero-Shot Pass Rate,
Self-Corrected Pass Rate, and Total Safety Violations.
"""

import sys
import os

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from typing import List, Dict, Any, Optional
import time
import json
import numpy as np
from pydantic import BaseModel, Field

from src.schemas.models import CloudSentryState, MetricPoint
from src.tools.metric_generator import MetricGenerator
from src.tools.k8s_sandbox import KubernetesSandboxValidator
from src.agents.orchestrator import CloudSentryOrchestrator


class ScenarioTrialResult(BaseModel):
    """Execution metrics for an individual benchmark scenario."""
    scenario_id: str
    target_service: str
    scenario_type: str
    detected_service: Optional[str] = None
    detected_failure_mode: Optional[str] = None
    culprit_correct: bool = False
    remediated: bool = False
    attempts: int = 0
    zero_shot_pass: bool = False
    self_corrected_pass: bool = False
    safety_violation: bool = False
    elapsed_ms: float = 0.0


class BenchmarkReport(BaseModel):
    """Consolidated quantitative performance evaluation report."""
    total_scenarios: int
    detection_accuracy_pct: float
    mean_time_to_resolution_ms: float
    zero_shot_patch_pass_rate_pct: float
    self_corrected_pass_rate_pct: float
    overall_remediation_success_pct: float
    total_safety_violations_pct: float
    failure_mode_breakdown: Dict[str, Dict[str, Any]]
    trials: List[ScenarioTrialResult] = Field(default_factory=list)


class BenchmarkSuite:
    """Executes multi-scenario empirical evaluation and computes SRE performance metrics."""

    FAILURE_MODES = [
        "OOM_KILL",
        "CPU_THROTTLING",
        "FINOPS_BUDGET_BREACH",
    ]

    SERVICES = [
        "checkout-service",
        "payment-service",
        "auth-service",
        "inventory-service",
    ]

    def __init__(self, random_seed: int = 42):
        self.random_seed = random_seed
        self.sandbox = KubernetesSandboxValidator()
        self.orchestrator = CloudSentryOrchestrator(use_langgraph=True)

    def generate_scenarios(self, total_scenarios: int = 50) -> List[Dict[str, Any]]:
        """Generates a balanced matrix of diverse failure scenarios across services and modes."""
        scenarios: List[Dict[str, Any]] = []
        rng = np.random.RandomState(self.random_seed)

        for i in range(total_scenarios):
            mode = self.FAILURE_MODES[i % len(self.FAILURE_MODES)]
            service = self.SERVICES[i % len(self.SERVICES)]
            seed = int(rng.randint(100, 10000))
            steps = int(rng.choice([18, 20, 22]))

            scenarios.append({
                "scenario_id": f"SCENARIO-{i+1:03d}",
                "target_service": service,
                "scenario_type": mode,
                "seed": seed,
                "num_steps": steps,
            })

        return scenarios

    def run(self, total_scenarios: int = 50) -> BenchmarkReport:
        """Runs the benchmark suite across all scenarios and compiles the report."""
        scenario_configs = self.generate_scenarios(total_scenarios)
        trials: List[ScenarioTrialResult] = []

        for sc in scenario_configs:
            # Generate synthetic metrics
            generator = MetricGenerator(random_seed=sc["seed"])
            telemetry = generator.generate_cluster_telemetry(
                culprit_service=sc["target_service"],
                culprit_scenario=sc["scenario_type"],
                num_steps=sc["num_steps"],
            )

            # Measure MTTR execution time
            start_time = time.perf_counter()
            final_state = self.orchestrator.run(telemetry)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            # Evaluate outcomes
            detected_culprit = final_state.rca.culprit_service if final_state.rca else None
            detected_mode = final_state.rca.primary_failure_mode if final_state.rca else None
            culprit_correct = (detected_culprit == sc["target_service"])

            attempts = final_state.iteration_count
            is_remediated = (final_state.status == "REMEDIATED")
            zero_shot = is_remediated and (attempts == 1)
            self_corrected = is_remediated and (attempts > 1)

            # Safety check: ensure no invalid manifest escapes
            safety_violation = False
            if is_remediated and final_state.patch:
                val = self.sandbox.validate_patch(final_state.patch)
                if not val.is_valid:
                    safety_violation = True

            trials.append(
                ScenarioTrialResult(
                    scenario_id=sc["scenario_id"],
                    target_service=sc["target_service"],
                    scenario_type=sc["scenario_type"],
                    detected_service=detected_culprit,
                    detected_failure_mode=detected_mode,
                    culprit_correct=culprit_correct,
                    remediated=is_remediated,
                    attempts=attempts,
                    zero_shot_pass=zero_shot,
                    self_corrected_pass=self_corrected,
                    safety_violation=safety_violation,
                    elapsed_ms=round(elapsed_ms, 2),
                )
            )

        # Aggregate Metrics
        total = len(trials)
        correct_detections = sum(1 for t in trials if t.culprit_correct)
        remediated_count = sum(1 for t in trials if t.remediated)
        zero_shot_count = sum(1 for t in trials if t.zero_shot_pass)
        self_corrected_count = sum(1 for t in trials if t.self_corrected_pass)
        safety_violations_count = sum(1 for t in trials if t.safety_violation)
        mean_mttr = sum(t.elapsed_ms for t in trials) / max(1, total)

        # Breakdown by failure mode
        mode_breakdown: Dict[str, Dict[str, Any]] = {}
        for mode in self.FAILURE_MODES:
            mode_trials = [t for t in trials if t.scenario_type == mode]
            if mode_trials:
                m_total = len(mode_trials)
                m_correct = sum(1 for t in mode_trials if t.culprit_correct)
                m_remediated = sum(1 for t in mode_trials if t.remediated)
                m_mttr = sum(t.elapsed_ms for t in mode_trials) / m_total
                mode_breakdown[mode] = {
                    "count": m_total,
                    "accuracy_pct": round((m_correct / m_total) * 100.0, 2),
                    "remediated_pct": round((m_remediated / m_total) * 100.0, 2),
                    "mean_mttr_ms": round(m_mttr, 2),
                }

        report = BenchmarkReport(
            total_scenarios=total,
            detection_accuracy_pct=round((correct_detections / total) * 100.0, 2),
            mean_time_to_resolution_ms=round(mean_mttr, 2),
            zero_shot_patch_pass_rate_pct=round((zero_shot_count / total) * 100.0, 2),
            self_corrected_pass_rate_pct=round((self_corrected_count / total) * 100.0, 2),
            overall_remediation_success_pct=round((remediated_count / total) * 100.0, 2),
            total_safety_violations_pct=round((safety_violations_count / total) * 100.0, 2),
            failure_mode_breakdown=mode_breakdown,
            trials=trials,
        )

        return report

    def export_report(self, report: BenchmarkReport, output_path: str = "data/benchmark_report.json") -> str:
        """Serializes report to JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))
        return output_path


def run_benchmark(
    total_scenarios: int = 50,
    output_path: str = "data/benchmark_report.json",
) -> BenchmarkReport:
    """Convenience entrypoint to execute benchmark suite and export metrics."""
    suite = BenchmarkSuite()
    report = suite.run(total_scenarios=total_scenarios)
    suite.export_report(report, output_path=output_path)
    return report


if __name__ == "__main__":
    print("[*] Running CloudSentry Benchmark Suite (50 Scenarios)...")
    rep = run_benchmark(total_scenarios=50)
    print("=" * 60)
    print("[+] CloudSentry Quantitative Benchmark Summary")
    print("=" * 60)
    print(f"* Total Evaluated Scenarios:       {rep.total_scenarios}")
    print(f"* Detection Accuracy:              {rep.detection_accuracy_pct}%")
    print(f"* Mean Time to Resolution (MTTR):  {rep.mean_time_to_resolution_ms} ms")
    print(f"* Zero-Shot Patch Pass Rate:       {rep.zero_shot_patch_pass_rate_pct}%")
    print(f"* Self-Corrected Pass Rate:        {rep.self_corrected_pass_rate_pct}%")
    print(f"* Overall Remediation Success:     {rep.overall_remediation_success_pct}%")
    print(f"* Total Safety Violations:         {rep.total_safety_violations_pct}%")
    print("=" * 60)
    print(f"[+] Report saved to data/benchmark_report.json")
