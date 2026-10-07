"""Tests for CloudSentry empirical evaluation benchmark engine.
"""

import os
import json
import pytest
from src.evaluation.benchmark import BenchmarkSuite, run_benchmark, BenchmarkReport


def test_benchmark_scenario_generation():
    """Verifies balanced scenario generation across failure modes and services."""
    suite = BenchmarkSuite(random_seed=42)
    scenarios = suite.generate_scenarios(total_scenarios=12)

    assert len(scenarios) == 12
    modes = {s["scenario_type"] for s in scenarios}
    services = {s["target_service"] for s in scenarios}

    assert "OOM_KILL" in modes
    assert "CPU_THROTTLING" in modes
    assert "FINOPS_BUDGET_BREACH" in modes
    assert "checkout-service" in services


def test_benchmark_smoke_run(tmp_path):
    """Executes a 5-sample smoke benchmark run and asserts metric validity."""
    output_file = str(tmp_path / "smoke_report.json")
    suite = BenchmarkSuite(random_seed=123)

    report = suite.run(total_scenarios=5)
    suite.export_report(report, output_path=output_file)

    # Validate report metrics
    assert report.total_scenarios == 5
    assert report.detection_accuracy_pct >= 80.0
    assert report.mean_time_to_resolution_ms > 0.0
    assert report.overall_remediation_success_pct >= 80.0
    assert report.total_safety_violations_pct == 0.0
    assert len(report.trials) == 5

    # Check exported JSON file
    assert os.path.exists(output_file)
    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["total_scenarios"] == 5
    assert "failure_mode_breakdown" in data
    assert len(data["trials"]) == 5
