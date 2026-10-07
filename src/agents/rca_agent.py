"""Root Cause Analysis (RCA) Agent for CloudSentry.

Correlates telemetry metrics, anomaly severity, and time-series degradation slopes
to isolate the root culprit service and classify the underlying failure mode.
"""

from typing import List, Dict, Optional
import pandas as pd
import numpy as np

from src.schemas.models import CloudSentryState, RootCauseAnalysis, MetricPoint, AnomalyReport


class RCAAgent:
    """Agent responsible for multi-metric correlation and root cause isolation."""

    def process(self, state: CloudSentryState) -> CloudSentryState:
        """Analyzes anomaly reports and metric trends to determine the primary failure mode."""
        state.log("[RCAAgent] Commencing multi-variate Root Cause Analysis correlation.")

        if not state.anomalies:
            state.log("[RCAAgent] No anomaly reports available to diagnose.")
            return state

        # Find highest severity anomalies
        anomalous_reports = [r for r in state.anomalies if r.anomaly_detected]
        if not anomalous_reports:
            state.log("[RCAAgent] No anomalous services identified.")
            return state

        # Severity ranking map
        severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        anomalous_reports.sort(
            key=lambda r: severity_rank.get(r.severity, 0), reverse=True
        )

        culprit_report = anomalous_reports[0]
        culprit_service = culprit_report.service_name

        # Extract metric points for the culprit service
        culprit_metrics = [m for m in state.metrics if m.service_name == culprit_service]
        culprit_metrics.sort(key=lambda m: m.timestamp)

        evidence_logs: List[str] = [
            f"Culprit service '{culprit_service}' flagged with {culprit_report.severity} severity.",
            culprit_report.summary,
        ]

        # Analyze metric signatures to classify failure mode
        df = pd.DataFrame([m.model_dump() for m in culprit_metrics]) if culprit_metrics else pd.DataFrame()

        primary_failure_mode = "OOM_KILL"
        confidence_score = 0.85

        if not df.empty:
            mem_series = df["memory_usage_mb"]
            cpu_series = df["cpu_usage_pct"]
            err_series = df["error_rate_pct"]
            lat_series = df["p99_latency_ms"]

            # Compute slopes and peaks
            x = np.arange(len(df))
            mem_slope, _ = np.polyfit(x, mem_series.values, 1) if len(df) > 1 else (0, 0)
            cpu_peak = cpu_series.max()
            mem_peak = mem_series.max()
            err_peak = err_series.max()
            lat_peak = lat_series.max()

            evidence_logs.append(
                f"Peak Telemetry -> Memory: {mem_peak:.1f}MB, CPU: {cpu_peak:.1f}%, Error Rate: {err_peak:.2f}%, P99 Latency: {lat_peak:.1f}ms."
            )

            # Classify
            if mem_slope > 20 and mem_peak > 600:
                primary_failure_mode = "OOM_KILL"
                confidence_score = min(0.98, 0.85 + (mem_slope / 500.0) + (err_peak / 100.0))
                evidence_logs.append(
                    f"Diagnosed memory leak: monotonic upward slope of {mem_slope:.2f} MB/step leading to container OOM kills."
                )
            elif cpu_peak > 85.0 and cpu_series.mean() > 70.0:
                primary_failure_mode = "CPU_THROTTLING"
                confidence_score = 0.92
                evidence_logs.append(
                    f"Diagnosed CPU exhaustion: sustained CPU usage > 85% causing request queue starvation."
                )
            elif lat_peak > 300.0:
                primary_failure_mode = "LATENCY_SPIKE"
                confidence_score = 0.88
                evidence_logs.append(
                    f"Diagnosed latency degradation: P99 latency reached {lat_peak:.1f}ms."
                )

        state.rca = RootCauseAnalysis(
            culprit_service=culprit_service,
            primary_failure_mode=primary_failure_mode,
            evidence_logs=evidence_logs,
            confidence_score=round(confidence_score, 3),
        )

        state.log(
            f"[RCAAgent] Root Cause identified: service='{culprit_service}', failure_mode='{primary_failure_mode}', confidence={state.rca.confidence_score}."
        )
        state.status = "PATCHING"
        return state


def run_rca_agent(state: CloudSentryState) -> CloudSentryState:
    """Functional node entrypoint for LangGraph / Orchestrator workflow."""
    agent = RCAAgent()
    return agent.process(state)
