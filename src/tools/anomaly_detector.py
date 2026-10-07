"""Anomaly detection engine for CloudSentry telemetry.

Combines rolling statistical Z-score algorithms and scikit-learn Isolation Forest
to detect memory leaks, CPU thrashing, and error surges across microservices.
"""

from typing import List, Dict, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src.schemas.models import MetricPoint, AnomalyReport


class MetricAnomalyDetector:
    """Detects multi-variate and single-variate anomalies in service telemetry streams."""

    def __init__(
        self,
        z_score_threshold: float = 2.5,
        contamination: float = 0.15,
        min_samples_for_ml: int = 8,
    ):
        self.z_score_threshold = z_score_threshold
        self.contamination = contamination
        self.min_samples_for_ml = min_samples_for_ml

    def detect_service_anomalies(
        self, service_name: str, metrics: List[MetricPoint]
    ) -> AnomalyReport:
        """Analyzes a specific service's metric points and produces an AnomalyReport."""
        if not metrics:
            return AnomalyReport(
                service_name=service_name,
                anomaly_detected=False,
                summary=f"No metrics available for service '{service_name}'",
            )

        # Convert to pandas DataFrame for time-series / statistical evaluation
        df = pd.DataFrame([m.model_dump() for m in metrics])
        df = df.sort_values(by="timestamp").reset_index(drop=True)

        feature_cols = ["cpu_usage_pct", "memory_usage_mb", "error_rate_pct", "p99_latency_ms"]

        # 1. Statistical Rolling & Threshold Analysis
        anomalies_found: List[str] = []
        trigger_metrics: List[str] = []
        max_severity = "LOW"

        # Check memory leak pattern (consistent upward slope + high memory delta)
        mem_series = df["memory_usage_mb"]
        if len(mem_series) >= 5:
            mem_diff = mem_series.iloc[-1] - mem_series.iloc[0]
            mem_growth_pct = (mem_diff / max(1.0, mem_series.iloc[0])) * 100
            
            # Linear trend slope
            x = np.arange(len(mem_series))
            slope, _ = np.polyfit(x, mem_series.values, 1)
            
            if mem_growth_pct > 80 and slope > 15:
                anomalies_found.append(
                    f"Memory leak detected: grew from {mem_series.iloc[0]:.1f}MB to {mem_series.iloc[-1]:.1f}MB (+{mem_growth_pct:.1f}%, slope={slope:.2f} MB/step)"
                )
                trigger_metrics.append("memory_usage_mb")
                max_severity = "CRITICAL" if mem_series.iloc[-1] > 1000 else "HIGH"

        # Check error rate surges
        err_series = df["error_rate_pct"]
        if err_series.max() > 5.0 or (err_series.iloc[-1] > 2.0 and err_series.iloc[-1] > err_series.iloc[0] * 3):
            anomalies_found.append(
                f"Error rate surge: peak {err_series.max():.2f}% (final: {err_series.iloc[-1]:.2f}%)"
            )
            trigger_metrics.append("error_rate_pct")
            if max_severity != "CRITICAL":
                max_severity = "HIGH" if err_series.max() > 10.0 else "MEDIUM"

        # Check CPU saturation / thrashing
        cpu_series = df["cpu_usage_pct"]
        if cpu_series.iloc[-3:].mean() > 85.0:
            anomalies_found.append(
                f"Sustained CPU saturation: recent avg {cpu_series.iloc[-3:].mean():.1f}%"
            )
            trigger_metrics.append("cpu_usage_pct")
            if max_severity not in ["CRITICAL", "HIGH"]:
                max_severity = "HIGH"

        # Check Latency spikes
        lat_series = df["p99_latency_ms"]
        if lat_series.iloc[-1] > lat_series.mean() + 2 * (lat_series.std() if lat_series.std() > 0 else 10):
            anomalies_found.append(
                f"P99 Latency spike: {lat_series.iloc[-1]:.1f}ms (mean baseline: {lat_series.mean():.1f}ms)"
            )
            trigger_metrics.append("p99_latency_ms")
            if max_severity == "LOW":
                max_severity = "MEDIUM"

        # 2. Isolation Forest Outlier Analysis
        ml_score: Optional[float] = None
        if len(df) >= self.min_samples_for_ml:
            try:
                features = df[feature_cols].values
                iso_forest = IsolationForest(
                    contamination=self.contamination, random_state=42, n_estimators=50
                )
                preds = iso_forest.fit_predict(features)
                scores = iso_forest.decision_function(features)
                ml_score = float(scores[-1])

                # Outlier identified at recent step
                if preds[-1] == -1 and not anomalies_found:
                    anomalies_found.append(
                        f"Isolation Forest identified multi-variate anomaly (score: {ml_score:.3f})"
                    )
                    trigger_metrics.append("multivariate_anomaly")
                    max_severity = "MEDIUM"
            except Exception:
                pass

        anomaly_detected = len(anomalies_found) > 0
        primary_trigger = trigger_metrics[0] if trigger_metrics else None

        if anomaly_detected:
            summary = (
                f"Anomaly detected in '{service_name}' [Severity: {max_severity}]. "
                + "; ".join(anomalies_found)
            )
        else:
            summary = f"Service '{service_name}' operating within nominal statistical thresholds."

        return AnomalyReport(
            service_name=service_name,
            anomaly_detected=anomaly_detected,
            trigger_metric=primary_trigger,
            severity=max_severity if anomaly_detected else "LOW",
            summary=summary,
            anomaly_score=ml_score,
        )

    def analyze_all(self, metrics: List[MetricPoint]) -> List[AnomalyReport]:
        """Groups telemetry metrics by service and produces reports for each service."""
        grouped: Dict[str, List[MetricPoint]] = {}
        for m in metrics:
            grouped.setdefault(m.service_name, []).append(m)

        reports: List[AnomalyReport] = []
        for service_name, service_metrics in grouped.items():
            report = self.detect_service_anomalies(service_name, service_metrics)
            reports.append(report)

        return reports


def detect_anomalies(metrics: List[MetricPoint]) -> List[AnomalyReport]:
    """Convenience helper function to run anomaly detection across all metrics."""
    detector = MetricAnomalyDetector()
    return detector.analyze_all(metrics)
