"""Root Cause Analysis (RCA) Agent for CloudSentry.

Correlates telemetry metrics, anomaly severity, and time-series degradation slopes
to isolate the root culprit service and classify the underlying failure mode using
LLM structured reasoning (Gemini/Groq) with automatic deterministic offline fallback.
"""

from typing import List, Dict, Optional, Any
import json
import pandas as pd
import numpy as np

from src.schemas.models import CloudSentryState, RootCauseAnalysis, MetricPoint, AnomalyReport
from src.tools.llm_provider import invoke_structured_llm, is_llm_available, get_chat_model


RCA_SYSTEM_PROMPT = """You are CloudSentry's Root Cause Analysis AI Engine for distributed cloud microservices.
Analyze the provided anomaly diagnostic reports, time-series metric trends, and cluster telemetry.
Tasks:
1. Identify the primary culprit microservice causing cluster degradation.
2. Classify the root failure mode strictly as one of:
   - "OOM_KILL": Memory leak, monotonically rising memory usage, late-stage error rate surge, or pod restarts.
   - "CPU_THROTTLING": High sustained CPU saturation (>85%), compute starvation, latency queuing.
   - "LATENCY_SPIKE": Sudden latency jump with normal memory/CPU, lock contention, or upstream bottlenecks.
3. Provide concise, factual evidence logs detailing peak memory, CPU, error rates, and growth slopes.
4. Assign an empirical confidence score between 0.0 and 1.0.

Respond strictly conforming to the RootCauseAnalysis schema.
"""


class RCAAgent:
    """Agent responsible for multi-metric correlation and root cause isolation."""

    def __init__(self, chat_model: Optional[Any] = None, enable_llm: bool = True):
        self.chat_model = chat_model
        self.enable_llm = enable_llm

    def _diagnose_with_llm(self, state: CloudSentryState) -> Optional[RootCauseAnalysis]:
        """Attempts LLM-powered structured diagnosis via LangChain / Gemini / Groq."""
        if not self.enable_llm and self.chat_model is None:
            return None

        # Build prompt payload
        anomalies_data = [a.model_dump() for a in state.anomalies if a.anomaly_detected]
        
        # Summary of metrics by service
        service_summaries: Dict[str, Dict[str, Any]] = {}
        for m in state.metrics:
            s = service_summaries.setdefault(m.service_name, {
                "max_cpu": 0.0, "max_mem": 0.0, "max_err": 0.0, "max_lat": 0.0, "count": 0
            })
            s["max_cpu"] = max(s["max_cpu"], m.cpu_usage_pct)
            s["max_mem"] = max(s["max_mem"], m.memory_usage_mb)
            s["max_err"] = max(s["max_err"], m.error_rate_pct)
            s["max_lat"] = max(s["max_lat"], m.p99_latency_ms)
            s["count"] += 1

        user_prompt = f"""Cluster Telemetry Summary:
{json.dumps(service_summaries, indent=2)}

Flagged Anomaly Reports:
{json.dumps(anomalies_data, indent=2)}

Please analyze the root cause and output a structured RootCauseAnalysis.
"""
        return invoke_structured_llm(
            schema=RootCauseAnalysis,
            system_prompt=RCA_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=self.chat_model,
        )

    def _diagnose_deterministic(self, state: CloudSentryState) -> Optional[RootCauseAnalysis]:
        """Fallback deterministic heuristic correlation engine."""
        anomalous_reports = [r for r in state.anomalies if r.anomaly_detected]
        if not anomalous_reports:
            return None

        # Severity ranking map
        severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        anomalous_reports.sort(
            key=lambda r: severity_rank.get(r.severity, 0), reverse=True
        )

        culprit_report = anomalous_reports[0]
        culprit_service = culprit_report.service_name

        # Extract metric points for culprit service
        culprit_metrics = [m for m in state.metrics if m.service_name == culprit_service]
        culprit_metrics.sort(key=lambda m: m.timestamp)

        evidence_logs: List[str] = [
            f"Culprit service '{culprit_service}' flagged with {culprit_report.severity} severity.",
            culprit_report.summary,
        ]

        df = pd.DataFrame([m.model_dump() for m in culprit_metrics]) if culprit_metrics else pd.DataFrame()

        primary_failure_mode = "OOM_KILL"
        confidence_score = 0.85

        if not df.empty:
            mem_series = df["memory_usage_mb"]
            cpu_series = df["cpu_usage_pct"]
            err_series = df["error_rate_pct"]
            lat_series = df["p99_latency_ms"]

            x = np.arange(len(df))
            mem_slope, _ = np.polyfit(x, mem_series.values, 1) if len(df) > 1 else (0, 0)
            cpu_peak = cpu_series.max()
            mem_peak = mem_series.max()
            err_peak = err_series.max()
            lat_peak = lat_series.max()

            evidence_logs.append(
                f"Peak Telemetry -> Memory: {mem_peak:.1f}MB, CPU: {cpu_peak:.1f}%, Error Rate: {err_peak:.2f}%, P99 Latency: {lat_peak:.1f}ms."
            )

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

        return RootCauseAnalysis(
            culprit_service=culprit_service,
            primary_failure_mode=primary_failure_mode,
            evidence_logs=evidence_logs,
            confidence_score=round(confidence_score, 3),
        )

    def process(self, state: CloudSentryState) -> CloudSentryState:
        """Analyzes anomaly reports and metric trends to determine the primary failure mode."""
        state.log("[RCAAgent] Commencing multi-variate Root Cause Analysis correlation.")

        if not state.anomalies:
            state.log("[RCAAgent] No anomaly reports available to diagnose.")
            return state

        has_anomalies = any(r.anomaly_detected for r in state.anomalies)
        if not has_anomalies:
            state.log("[RCAAgent] No anomalous services identified.")
            return state

        # 1. Attempt LLM Diagnosis if enabled & keys configured
        rca_result: Optional[RootCauseAnalysis] = None
        if self.enable_llm or self.chat_model is not None:
            try:
                rca_result = self._diagnose_with_llm(state)
                if rca_result:
                    state.log(f"[RCAAgent] LLM reasoning completed: culprit='{rca_result.culprit_service}', mode='{rca_result.primary_failure_mode}'.")
            except Exception as e:
                state.log(f"[RCAAgent] LLM invocation encountered exception ({e}); falling back to deterministic heuristic.")
                rca_result = None

        # 2. Fall back to Deterministic Heuristic Engine
        if not rca_result:
            state.log("[RCAAgent] Using deterministic statistical correlation engine.")
            rca_result = self._diagnose_deterministic(state)

        if rca_result:
            state.rca = rca_result
            state.log(
                f"[RCAAgent] Root Cause identified: service='{rca_result.culprit_service}', failure_mode='{rca_result.primary_failure_mode}', confidence={rca_result.confidence_score}."
            )
            state.status = "PATCHING"
        else:
            state.log("[RCAAgent] Unable to isolate root cause.")

        return state


def run_rca_agent(state: CloudSentryState) -> CloudSentryState:
    """Functional node entrypoint for LangGraph / Orchestrator workflow."""
    agent = RCAAgent()
    return agent.process(state)
