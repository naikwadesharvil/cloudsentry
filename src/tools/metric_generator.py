"""Synthetic telemetry generator for CloudSentry incident simulation.

Generates realistic time-series metrics demonstrating memory leaks, CPU saturation,
latency spikes, and nominal microservice health across 20+ timestamps.
"""

from typing import List, Dict, Any, Optional
import json
import os
import numpy as np

from src.schemas.models import MetricPoint


class MetricGenerator:
    """Generates synthetic multi-service metric points for simulation and test harnesses."""

    def __init__(self, random_seed: int = 42):
        self.rng = np.random.RandomState(random_seed)

    def generate_service_metrics(
        self,
        service_name: str,
        num_steps: int = 20,
        scenario: str = "OOM_KILL",
    ) -> List[MetricPoint]:
        """Generates a time-series sequence of MetricPoints for a specific scenario."""
        points: List[MetricPoint] = []

        for t in range(num_steps):
            if scenario == "OOM_KILL":
                # Gradual linear memory leak with sharp escalation & late-stage error surge
                # Base nominal memory: 250MB. Leaks ~75MB per step up to ~1750MB.
                noise_mem = self.rng.normal(0, 8.0)
                mem = 250.0 + (t * 75.0) + noise_mem

                # CPU remains moderate until OOM restarts trigger thrashing
                cpu = 28.0 + (t * 1.5) + self.rng.normal(0, 3.0)
                if t >= 15:
                    cpu += 20.0  # GC churn / restart thrashing

                # Error rate stays nominal (<0.2%) until memory pressure/OOM kills hit at step 14+
                if t < 14:
                    err = max(0.01, 0.1 + self.rng.normal(0, 0.05))
                    latency = 45.0 + (t * 2.0) + self.rng.normal(0, 3.0)
                else:
                    err = 4.0 + ((t - 14) * 3.5) + self.rng.uniform(0.5, 2.0)
                    latency = 120.0 + ((t - 14) * 140.0) + self.rng.uniform(10, 30)

            elif scenario == "CPU_THROTTLING":
                # CPU shoots to near 100% capacity; memory stays flat; latency explodes
                cpu = min(99.5, 40.0 + (t * 3.5) + self.rng.normal(0, 2.0))
                mem = 300.0 + self.rng.normal(0, 10.0)
                err = max(0.01, (0.05 + ((t / 20.0) * 8.0) if t > 12 else 0.1))
                latency = 50.0 + ((t ** 2) * 2.5) + self.rng.normal(0, 10.0)

            elif scenario == "LATENCY_SPIKE":
                # Upstream bottleneck or lock contention
                cpu = 35.0 + self.rng.normal(0, 4.0)
                mem = 280.0 + self.rng.normal(0, 8.0)
                latency = 60.0 + (750.0 if t > 12 else 0.0) + self.rng.normal(0, 15.0)
                err = 0.2 + (5.0 if t > 14 else 0.0)

            elif scenario in ["FINOPS_BUDGET_BREACH", "RUNAWAY_REPLICAS"]:
                # Massive compute/memory runaway breach
                cpu = min(98.0, 35.0 + (t * 3.2) + self.rng.normal(0, 3.0))
                mem = 250.0 + (t * 85.0) + self.rng.normal(0, 10.0)
                err = max(0.01, 0.05 + ((t / 20.0) * 12.0) if t > 12 else 0.1)
                latency = 45.0 + ((t ** 1.8) * 2.0) + self.rng.normal(0, 5.0)

            else:  # HEALTHY
                cpu = max(5.0, 22.0 + self.rng.normal(0, 4.0))
                mem = max(100.0, 240.0 + self.rng.normal(0, 12.0))
                err = max(0.0, min(1.0, 0.08 + self.rng.normal(0, 0.03)))
                latency = max(20.0, 42.0 + self.rng.normal(0, 5.0))

            points.append(
                MetricPoint(
                    timestamp=t,
                    service_name=service_name,
                    cpu_usage_pct=round(float(cpu), 2),
                    memory_usage_mb=round(float(mem), 2),
                    error_rate_pct=round(float(err), 2),
                    p99_latency_ms=round(float(latency), 2),
                )
            )

        return points

    def generate_cluster_telemetry(
        self,
        culprit_service: str = "checkout-service",
        culprit_scenario: str = "OOM_KILL",
        num_steps: int = 20,
    ) -> List[MetricPoint]:
        """Generates a composite telemetry stream containing both healthy and degraded services."""
        all_metrics: List[MetricPoint] = []

        # Culprit microservice
        culprit_metrics = self.generate_service_metrics(
            service_name=culprit_service,
            num_steps=num_steps,
            scenario=culprit_scenario,
        )
        all_metrics.extend(culprit_metrics)

        # Peer healthy services in the distributed cluster
        all_cluster_services = ["checkout-service", "auth-service", "payment-service", "inventory-service"]
        healthy_services = [s for s in all_cluster_services if s != culprit_service]
        for svc in healthy_services:
            svc_metrics = self.generate_service_metrics(
                service_name=svc,
                num_steps=num_steps,
                scenario="HEALTHY",
            )
            all_metrics.extend(svc_metrics)

        # Sort interleaved telemetry by timestamp
        all_metrics.sort(key=lambda p: (p.timestamp, p.service_name))
        return all_metrics

    def save_telemetry_to_file(
        self, metrics: List[MetricPoint], output_path: str
    ) -> str:
        """Serializes telemetry metric points to a JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        data = [m.model_dump() for m in metrics]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return output_path


def generate_incident_telemetry(
    output_file: Optional[str] = None,
    culprit_service: str = "checkout-service",
    num_steps: int = 20,
) -> List[MetricPoint]:
    """Generates standard checkout-service OOM incident metrics and optionally saves them."""
    generator = MetricGenerator()
    telemetry = generator.generate_cluster_telemetry(
        culprit_service=culprit_service,
        culprit_scenario="OOM_KILL",
        num_steps=num_steps,
    )
    if output_file:
        generator.save_telemetry_to_file(telemetry, output_file)
    return telemetry
