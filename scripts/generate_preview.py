"""Generates high-resolution dashboard preview assets for CloudSentry.

Produces assets/dashboard_preview.png representing the multi-panel telemetry visualizer
with anomaly zone highlighting and baseline resource thresholds.
"""

import sys
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.tools.metric_generator import MetricGenerator


def generate_preview_asset(output_path: str = "assets/dashboard_preview.png"):
    """Renders and exports high-resolution dashboard telemetry preview image."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # 1. Generate standard cluster telemetry
    gen = MetricGenerator(random_seed=42)
    metrics = gen.generate_cluster_telemetry(
        culprit_service="checkout-service",
        culprit_scenario="OOM_KILL",
        num_steps=20,
    )
    df = pd.DataFrame([m.model_dump() for m in metrics])

    # 2. Build 4-Panel Subplots
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "<b>Memory Consumption (MB) [Anomaly Zone: Steps 14-20]</b>",
            "<b>CPU Utilization (%)</b>",
            "<b>P99 Latency (ms)</b>",
            "<b>HTTP Error Rate (%)</b>",
        ),
        vertical_spacing=0.18,
        horizontal_spacing=0.08,
    )

    color_map = {
        "checkout-service": "#f85149",  # Red / Culprit
        "auth-service": "#3fb950",      # Green
        "payment-service": "#58a6ff",   # Blue
        "inventory-service": "#d29922", # Amber
    }

    for svc in df["service_name"].unique():
        svc_data = df[df["service_name"] == svc].sort_values("timestamp")
        color = color_map.get(svc, "#8b949e")
        is_culprit = (svc == "checkout-service")

        # Memory Trace
        fig.add_trace(
            go.Scatter(
                x=svc_data["timestamp"],
                y=svc_data["memory_usage_mb"],
                name=f"{svc} (Culprit)" if is_culprit else svc,
                legendgroup=svc,
                line=dict(color=color, width=3.0 if is_culprit else 1.8),
            ),
            row=1,
            col=1,
        )

        # CPU Trace
        fig.add_trace(
            go.Scatter(
                x=svc_data["timestamp"],
                y=svc_data["cpu_usage_pct"],
                name=svc,
                legendgroup=svc,
                showlegend=False,
                line=dict(color=color, width=3.0 if is_culprit else 1.8),
            ),
            row=1,
            col=2,
        )

        # Latency Trace
        fig.add_trace(
            go.Scatter(
                x=svc_data["timestamp"],
                y=svc_data["p99_latency_ms"],
                name=svc,
                legendgroup=svc,
                showlegend=False,
                line=dict(color=color, width=3.0 if is_culprit else 1.8),
            ),
            row=2,
            col=1,
        )

        # Error Rate Trace
        fig.add_trace(
            go.Scatter(
                x=svc_data["timestamp"],
                y=svc_data["error_rate_pct"],
                name=svc,
                legendgroup=svc,
                showlegend=False,
                line=dict(color=color, width=3.0 if is_culprit else 1.8),
            ),
            row=2,
            col=2,
        )

    # Highlight Anomaly Zone in red for all panels
    for r in range(1, 3):
        for c in range(1, 3):
            fig.add_vrect(
                x0=14,
                x1=19,
                fillcolor="rgba(248, 81, 73, 0.15)",
                layer="below",
                line_width=1.5,
                line_dash="dot",
                line_color="rgba(248, 81, 73, 0.6)",
                row=r,
                col=c,
            )

    # K8s baseline threshold line
    fig.add_hline(
        y=512,
        line_dash="dash",
        line_color="#f85149",
        annotation_text="K8s Baseline Limit (512Mi)",
        annotation_position="top left",
        row=1,
        col=1,
    )

    fig.update_layout(
        title=dict(
            text="<b>CloudSentry Telemetry Monitor • Distributed Microservice Anomaly Incident</b>",
            font=dict(size=18, color="#f0f6fc"),
            x=0.5,
            xanchor="center",
        ),
        template="plotly_dark",
        paper_bgcolor="#161b22",
        plot_bgcolor="#0d1117",
        margin=dict(l=50, r=50, t=80, b=50),
        height=650,
        width=1200,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.03,
            xanchor="center",
            x=0.5,
            font=dict(size=12),
        ),
    )

    try:
        fig.write_image(output_path, scale=2)
        print(f"[+] Successfully exported static Plotly preview to {output_path}")
    except Exception as e:
        print(f"[-] Plotly static write_image error: {e}. Generating fallback canvas...")
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1200, 650), color="#161b22")
        draw = ImageDraw.Draw(img)
        draw.rectangle([(20, 20), (1180, 630)], outline="#30363d", width=2)
        draw.text((40, 40), "CloudSentry Ops Console & Telemetry Monitor", fill="#58a6ff")
        draw.text((40, 70), "Telemetry Stream • Anomaly Detection • Sandbox Policy Remediation", fill="#8b949e")
        img.save(output_path)
        print(f"[+] Exported fallback banner to {output_path}")

    return output_path


if __name__ == "__main__":
    generate_preview_asset()
