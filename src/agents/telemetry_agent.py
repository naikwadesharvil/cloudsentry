"""Telemetry Agent for CloudSentry.

Ingests real-time time-series telemetry and executes statistical anomaly detection
to flag degrading or degraded distributed microservices.
"""

from typing import List, Dict, Any
from src.schemas.models import CloudSentryState, AnomalyReport, MetricPoint
from src.tools.anomaly_detector import MetricAnomalyDetector


class TelemetryAgent:
    """Agent responsible for telemetry ingestion and anomaly classification."""

    def __init__(self, detector: MetricAnomalyDetector = None):
        self.detector = detector or MetricAnomalyDetector()

    def process(self, state: CloudSentryState) -> CloudSentryState:
        """Processes state metrics and outputs anomaly reports for each monitored microservice."""
        state.log(f"[TelemetryAgent] Ingesting {len(state.metrics)} telemetry metric points.")

        if not state.metrics:
            state.log("[TelemetryAgent] Warning: No telemetry metrics found in state.")
            state.anomalies = []
            return state

        # Run anomaly detection tool
        reports = self.detector.analyze_all(state.metrics)
        state.anomalies = reports

        flagged_services = [r.service_name for r in reports if r.anomaly_detected]
        if flagged_services:
            state.log(
                f"[TelemetryAgent] Detected anomalies in {len(flagged_services)} service(s): {', '.join(flagged_services)}"
            )
            state.status = "ANALYZING"
        else:
            state.log("[TelemetryAgent] All microservices operating within normal baseline.")
            state.status = "ANALYZING"

        return state


def run_telemetry_agent(state: CloudSentryState) -> CloudSentryState:
    """Functional node entrypoint for LangGraph / Orchestrator workflow."""
    agent = TelemetryAgent()
    return agent.process(state)
