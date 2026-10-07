"""CloudSentry One-Click Demo & Execution Runner.

Provides a unified command-line entrypoint to execute live incident remediation CLI demos,
trigger the quantitative benchmark suite, or launch the interactive Streamlit UI dashboard.

Usage:
  python run_demo.py           # Runs live CLI incident simulation & multi-agent loop
  python run_demo.py --ui      # Launches Streamlit web dashboard
  python run_demo.py --eval    # Executes 50-scenario quantitative benchmark suite
"""

import sys
import os
import argparse
import subprocess
import json

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.tools.metric_generator import generate_incident_telemetry
from src.agents.orchestrator import CloudSentryOrchestrator
from src.evaluation.benchmark import run_benchmark


def run_cli_demo(culprit_service: str = "checkout-service", scenario: str = "OOM_KILL", steps: int = 20):
    """Executes an end-to-end incident remediation simulation with formatted terminal trace."""
    print("=" * 72)
    print(" [CLOUDSENTRY] AUTONOMOUS FINOPS & INCIDENT REMEDIATION ENGINE")
    print("=" * 72)
    print(f"[*] Simulating Distributed Telemetry Incident...")
    print(f"    - Target Culprit:   {culprit_service}")
    print(f"    - Failure Scenario: {scenario}")
    print(f"    - Timestamps:       {steps} points per service")
    print("-" * 72)

    # 1. Telemetry Ingestion
    telemetry = generate_incident_telemetry(culprit_service=culprit_service, num_steps=steps)
    print(f"[+] Ingested {len(telemetry)} multi-service time-series metric points.")

    # 2. Multi-Agent DAG Execution
    orchestrator = CloudSentryOrchestrator(use_langgraph=True)
    final_state = orchestrator.run(telemetry)

    # 3. Output Trace
    print("\n[+] MULTI-AGENT DAG EXECUTION AUDIT:")
    for log_msg in final_state.history_logs:
        print(f"    {log_msg}")

    print("\n" + "=" * 72)
    print(" [*] FINAL REMEDIATION SUMMARY")
    print("=" * 72)

    if final_state.rca:
        print(f"[*] Diagnosed Culprit:      {final_state.rca.culprit_service}")
        print(f"[*] Failure Mode:           {final_state.rca.primary_failure_mode}")
        print(f"[*] Confidence Score:       {final_state.rca.confidence_score * 100:.1f}%")

    if final_state.validation:
        print(f"[*] Sandbox Validation:     {'PASSED (Compliant)' if final_state.validation.is_valid else 'FAILED'}")
        print(f"[*] Policy Violations:      {len(final_state.validation.policy_violations)}")
        print(f"[*] Iteration Attempts:     {final_state.iteration_count}")

    print(f"[*] Final System Status:    {final_state.status}")

    if final_state.patch and final_state.patch.diff_content:
        print("\n" + "-" * 72)
        print(" [!] SYNTHESIZED KUBERNETES MANIFEST DIFF:")
        print("-" * 72)
        print(final_state.patch.diff_content)
        print("-" * 72)
        print(f"[*] Reasoning: {final_state.patch.reasoning}")

    print("=" * 72)


def run_ui():
    """Launches the Streamlit operations dashboard."""
    app_path = os.path.join(os.path.dirname(__file__), "dashboard", "app.py")
    cmd = [sys.executable, "-m", "streamlit", "run", app_path]
    print("[*] Launching CloudSentry Streamlit Dashboard on http://localhost:8501...")
    subprocess.run(cmd)


def run_eval():
    """Executes the quantitative 50-scenario evaluation benchmark."""
    print("[*] Running CloudSentry 50-Scenario Quantitative Benchmark Suite...")
    report = run_benchmark(total_scenarios=50, output_path="data/benchmark_report.json")
    print("\n" + "=" * 72)
    print(" [CLOUDSENTRY] QUANTITATIVE BENCHMARK RESULTS")
    print("=" * 72)
    print(f"* Total Evaluated Scenarios:       {report.total_scenarios}")
    print(f"* Detection Accuracy:              {report.detection_accuracy_pct}%")
    print(f"* Mean Time to Resolution (MTTR):  {report.mean_time_to_resolution_ms} ms")
    print(f"* Zero-Shot Patch Pass Rate:       {report.zero_shot_patch_pass_rate_pct}%")
    print(f"* Overall Remediation Success:     {report.overall_remediation_success_pct}%")
    print(f"* Total Safety Violations:         {report.total_safety_violations_pct}%")
    print("=" * 72)
    print("[+] Report saved to: data/benchmark_report.json")


def run_viva(auto_mode: bool = False):
    """Launches the interactive or automated Viva Defense & Technical Interview Simulator."""
    from src.evaluation.viva_simulator import run_simulator
    run_simulator(auto_mode=auto_mode)


def main():
    parser = argparse.ArgumentParser(description="CloudSentry One-Click Demo Runner")
    parser.add_argument("--ui", action="store_true", help="Launch Streamlit Web Dashboard")
    parser.add_argument("--eval", action="store_true", help="Run 50-scenario benchmark suite")
    parser.add_argument("--viva", action="store_true", help="Run Viva Defense Simulator")
    parser.add_argument("--auto", action="store_true", help="Run in automated demo mode (for viva simulator)")
    parser.add_argument("--scenario", type=str, default="OOM_KILL", choices=["OOM_KILL", "CPU_THROTTLING", "LATENCY_SPIKE", "HEALTHY"], help="Incident scenario")
    parser.add_argument("--service", type=str, default="checkout-service", help="Culprit service")
    parser.add_argument("--steps", type=int, default=20, help="Simulation steps")

    args = parser.parse_args()

    if args.ui:
        run_ui()
    elif args.eval:
        run_eval()
    elif args.viva:
        run_viva(auto_mode=args.auto)
    else:
        run_cli_demo(culprit_service=args.service, scenario=args.scenario, steps=args.steps)


if __name__ == "__main__":
    main()
