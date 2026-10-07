"""CloudSentry Live Incident Triage & Autonomous Remediation Dashboard.

Interactive Streamlit application for visualizing distributed microservice telemetry,
triggering simulated incident outages, observing multi-agent DAG execution traces,
and inspecting FinOps Kubernetes YAML remediation diffs.
"""

import sys
import os

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yaml

from src.schemas.models import CloudSentryState, MetricPoint
from src.tools.metric_generator import MetricGenerator
from src.tools.k8s_sandbox import KubernetesSandboxValidator
from src.tools.llm_provider import get_api_key_provider, is_llm_available
from src.agents.telemetry_agent import run_telemetry_agent
from src.agents.rca_agent import run_rca_agent
from src.agents.patch_agent import run_patch_agent
from src.agents.validator_agent import run_validator_agent
from src.agents.orchestrator import CloudSentryOrchestrator


# -----------------------------------------------------------------------------
# Streamlit App Configuration & Custom Theme
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="CloudSentry | Autonomous FinOps SRE",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Sleek Dark Operations Styling
st.markdown(
    """
    <style>
    /* Global Styles */
    .stApp {
        background-color: #0d1117;
        color: #c9d1d9;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Header Card */
    .main-header {
        background: linear-gradient(135deg, #161b22 0%, #1f2937 100%);
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    }
    
    /* Health Badge Cards */
    .service-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .service-card:hover {
        border-color: #58a6ff;
        transform: translateY(-2px);
    }
    
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }
    .badge-healthy {
        background-color: rgba(46, 160, 67, 0.15);
        color: #3fb950;
        border: 1px solid rgba(46, 160, 67, 0.4);
    }
    .badge-degraded {
        background-color: rgba(248, 81, 73, 0.15);
        color: #f85149;
        border: 1px solid rgba(248, 81, 73, 0.4);
    }
    .badge-remediated {
        background-color: rgba(88, 166, 255, 0.15);
        color: #58a6ff;
        border: 1px solid rgba(88, 166, 255, 0.4);
    }

    /* Agent DAG Node Cards */
    .dag-node {
        background-color: #161b22;
        border-left: 4px solid #58a6ff;
        border-radius: 6px;
        padding: 16px;
        margin-bottom: 12px;
        border-top: 1px solid #21262d;
        border-right: 1px solid #21262d;
        border-bottom: 1px solid #21262d;
    }
    .dag-node-alert {
        border-left-color: #f85149;
    }
    .dag-node-success {
        border-left-color: #3fb950;
    }
    
    /* Code Diff Styling */
    .diff-added {
        background-color: rgba(46, 160, 67, 0.2);
        color: #7ee787;
        padding: 2px 4px;
        border-radius: 4px;
    }
    .diff-removed {
        background-color: rgba(248, 81, 73, 0.2);
        color: #ffa198;
        padding: 2px 4px;
        border-radius: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# State Management Initialization
# -----------------------------------------------------------------------------
if "incident_active" not in st.session_state:
    st.session_state.incident_active = False

if "remediation_state" not in st.session_state:
    st.session_state.remediation_state = None

if "telemetry_metrics" not in st.session_state:
    gen = MetricGenerator(random_seed=42)
    st.session_state.telemetry_metrics = gen.generate_cluster_telemetry(
        culprit_service="checkout-service",
        culprit_scenario="OOM_KILL",
        num_steps=20,
    )


# -----------------------------------------------------------------------------
# Sidebar Configuration
# -----------------------------------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/shield.png", width=64)
    st.title("CloudSentry Engine")
    st.caption("Autonomous Incident Remediation & FinOps Guardrails")
    st.divider()

    st.subheader("🎯 Incident Simulation Controls")
    selected_scenario = st.selectbox(
        "Failure Mode Scenario",
        options=["OOM_KILL", "CPU_THROTTLING", "LATENCY_SPIKE", "HEALTHY"],
        index=0,
        help="Simulate distinct distributed failure signatures across cluster workloads.",
    )

    culprit_service = st.selectbox(
        "Target Culprit Service",
        options=["checkout-service", "payment-service", "auth-service", "inventory-service"],
        index=0,
    )

    simulation_steps = st.slider(
        "Telemetry Timestamps", min_value=10, max_value=30, value=20, step=2
    )

    st.divider()
    st.subheader("🤖 Reasoning Engine")
    provider, _ = get_api_key_provider()
    if provider:
        st.success(f"Active Provider: **{provider.upper()}** (LLM Mode)")
    else:
        st.info("Active Provider: **Deterministic Heuristic Engine** (Offline Mode)")

    st.divider()
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        trigger_btn = st.button("🚨 Run Remediation", width="stretch", type="primary")
    with col_btn2:
        reset_btn = st.button("🔄 Reset Telemetry", width="stretch")

    if reset_btn:
        st.session_state.incident_active = False
        st.session_state.remediation_state = None
        gen = MetricGenerator(random_seed=42)
        st.session_state.telemetry_metrics = gen.generate_cluster_telemetry(
            culprit_service="checkout-service",
            culprit_scenario="HEALTHY",
            num_steps=simulation_steps,
        )
        st.rerun()

    if trigger_btn:
        st.session_state.incident_active = True
        gen = MetricGenerator(random_seed=42)
        st.session_state.telemetry_metrics = gen.generate_cluster_telemetry(
            culprit_service=culprit_service,
            culprit_scenario=selected_scenario,
            num_steps=simulation_steps,
        )
        # Execute Orchestrator
        orchestrator = CloudSentryOrchestrator(use_langgraph=True)
        st.session_state.remediation_state = orchestrator.run(
            st.session_state.telemetry_metrics
        )
        st.rerun()


# -----------------------------------------------------------------------------
# Header & System Health Bar
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div class="main-header">
        <h1 style="margin:0; font-size: 2rem; color: #58a6ff;">🛡️ CloudSentry Autonomous Operations Console</h1>
        <p style="margin:4px 0 0 0; color: #8b949e; font-size: 1rem;">
            Real-Time Telemetry Correlation • Multi-Agent Root Cause Analysis • Sandboxed FinOps Remediation
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

services_list = ["checkout-service", "auth-service", "payment-service", "inventory-service"]
health_cols = st.columns(len(services_list))

rem_state = st.session_state.remediation_state
culprit = rem_state.rca.culprit_service if (rem_state and rem_state.rca) else culprit_service
is_remediated = rem_state and rem_state.status == "REMEDIATED"

for idx, svc in enumerate(services_list):
    with health_cols[idx]:
        if st.session_state.incident_active and svc == culprit:
            if is_remediated:
                status_label = "Remediated"
                badge_class = "badge-remediated"
                health_icon = "🛡️"
            else:
                status_label = "Degraded"
                badge_class = "badge-degraded"
                health_icon = "⚠️"
        else:
            status_label = "Healthy"
            badge_class = "badge-healthy"
            health_icon = "✅"

        st.markdown(
            f"""
            <div class="service-card">
                <div style="font-size: 1.2rem; font-weight: 600; color: #f0f6fc; margin-bottom: 6px;">
                    {health_icon} {svc}
                </div>
                <span class="status-badge {badge_class}">{status_label}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.write("")

# -----------------------------------------------------------------------------
# Section 1: Interactive Telemetry Visualizer (Plotly Multi-Panel)
# -----------------------------------------------------------------------------
st.subheader("📊 Live Distributed Microservice Telemetry Stream")

metrics_df = pd.DataFrame([m.model_dump() for m in st.session_state.telemetry_metrics])

# Render 4-Panel Plotly Subplots
fig = make_subplots(
    rows=2,
    cols=2,
    subplot_titles=(
        "💾 Memory Consumption (MB)",
        "⚡ CPU Utilization (%)",
        "⏱️ P99 Latency (ms)",
        "🚨 Error Rate (%)",
    ),
    vertical_spacing=0.15,
    horizontal_spacing=0.08,
)

color_map = {
    "checkout-service": "#f85149",
    "auth-service": "#3fb950",
    "payment-service": "#58a6ff",
    "inventory-service": "#d29922",
}

for svc in metrics_df["service_name"].unique():
    svc_data = metrics_df[metrics_df["service_name"] == svc].sort_values("timestamp")
    color = color_map.get(svc, "#8b949e")

    # 1. Memory
    fig.add_trace(
        go.Scatter(
            x=svc_data["timestamp"],
            y=svc_data["memory_usage_mb"],
            name=svc,
            legendgroup=svc,
            line=dict(color=color, width=2.5 if svc == culprit else 1.5),
        ),
        row=1,
        col=1,
    )

    # 2. CPU
    fig.add_trace(
        go.Scatter(
            x=svc_data["timestamp"],
            y=svc_data["cpu_usage_pct"],
            name=svc,
            legendgroup=svc,
            showlegend=False,
            line=dict(color=color, width=2.5 if svc == culprit else 1.5),
        ),
        row=1,
        col=2,
    )

    # 3. Latency
    fig.add_trace(
        go.Scatter(
            x=svc_data["timestamp"],
            y=svc_data["p99_latency_ms"],
            name=svc,
            legendgroup=svc,
            showlegend=False,
            line=dict(color=color, width=2.5 if svc == culprit else 1.5),
        ),
        row=2,
        col=1,
    )

    # 4. Error Rate
    fig.add_trace(
        go.Scatter(
            x=svc_data["timestamp"],
            y=svc_data["error_rate_pct"],
            name=svc,
            legendgroup=svc,
            showlegend=False,
            line=dict(color=color, width=2.5 if svc == culprit else 1.5),
        ),
        row=2,
        col=2,
    )

# Highlight Anomaly Zone if active incident
if st.session_state.incident_active and simulation_steps >= 14:
    for r in range(1, 3):
        for c in range(1, 3):
            fig.add_vrect(
                x0=14,
                x1=simulation_steps - 1,
                fillcolor="rgba(248, 81, 73, 0.12)",
                layer="below",
                line_width=1,
                line_dash="dot",
                line_color="rgba(248, 81, 73, 0.4)",
                row=r,
                col=c,
            )

# Add baseline limit threshold on Memory chart
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
    template="plotly_dark",
    paper_bgcolor="#161b22",
    plot_bgcolor="#0d1117",
    margin=dict(l=40, r=40, t=40, b=30),
    height=480,
    legend=dict(orientation="h", yanchor="bottom", y=1.06, xanchor="right", x=1),
)

st.plotly_chart(fig, width="stretch")


# -----------------------------------------------------------------------------
# Section 2: Agent DAG Execution Trace
# -----------------------------------------------------------------------------
if rem_state:
    st.divider()
    st.subheader("⚡ Multi-Agent Incident Remediation Trace")

    trace_cols = st.columns(4)

    # 1. Telemetry Node
    with trace_cols[0]:
        anomalies_flagged = [a for a in rem_state.anomalies if a.anomaly_detected]
        node_status_class = "dag-node-alert" if anomalies_flagged else "dag-node-success"
        st.markdown(
            f"""
            <div class="dag-node {node_status_class}">
                <div style="font-weight:700; color:#58a6ff; margin-bottom:4px;">1. Telemetry Agent</div>
                <div style="font-size:0.85rem; color:#f0f6fc;">
                    Flagged: <b>{len(anomalies_flagged)} anomaly</b><br/>
                    Trigger: <span style="color:#f85149;">{anomalies_flagged[0].trigger_metric if anomalies_flagged else 'None'}</span><br/>
                    Severity: <b>{anomalies_flagged[0].severity if anomalies_flagged else 'NOMINAL'}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 2. RCA Node
    with trace_cols[1]:
        if rem_state.rca:
            st.markdown(
                f"""
                <div class="dag-node dag-node-alert">
                    <div style="font-weight:700; color:#58a6ff; margin-bottom:4px;">2. RCA Agent</div>
                    <div style="font-size:0.85rem; color:#f0f6fc;">
                        Culprit: <b>{rem_state.rca.culprit_service}</b><br/>
                        Mode: <span style="color:#f85149;">{rem_state.rca.primary_failure_mode}</span><br/>
                        Confidence: <b>{rem_state.rca.confidence_score * 100:.1f}%</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # 3. Patch Node
    with trace_cols[2]:
        if rem_state.patch:
            st.markdown(
                f"""
                <div class="dag-node dag-node-success">
                    <div style="font-weight:700; color:#58a6ff; margin-bottom:4px;">3. Patch Agent</div>
                    <div style="font-size:0.85rem; color:#f0f6fc;">
                        Target: <code>{os.path.basename(rem_state.patch.target_manifest)}</code><br/>
                        Action: <b>Resize Limits</b><br/>
                        Iteration: <b>Attempt {rem_state.iteration_count}</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # 4. Validator Node
    with trace_cols[3]:
        if rem_state.validation:
            v_color = "dag-node-success" if rem_state.validation.is_valid else "dag-node-alert"
            st.markdown(
                f"""
                <div class="dag-node {v_color}">
                    <div style="font-weight:700; color:#58a6ff; margin-bottom:4px;">4. Validator Sandbox</div>
                    <div style="font-size:0.85rem; color:#f0f6fc;">
                        Policy Status: <b>{'COMPLIANT' if rem_state.validation.is_valid else 'VIOLATION'}</b><br/>
                        Linter Errors: <b>{len(rem_state.validation.linter_errors)}</b><br/>
                        Outcome: <span style="color:#3fb950; font-weight:700;">{rem_state.status}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Diagnostic Logs Expander
    with st.expander("📝 Detailed Multi-Agent Audit Trail & Logs", expanded=False):
        for log_entry in rem_state.history_logs:
            st.text(f"• {log_entry}")


# -----------------------------------------------------------------------------
# Section 3: Unified Diff & Corrected Kubernetes Manifest
# -----------------------------------------------------------------------------
if rem_state and rem_state.patch:
    st.divider()
    st.subheader("🔍 FinOps Remediation: Manifest Diff & Corrected Manifest")

    diff_col1, diff_col2 = st.columns(2)

    with diff_col1:
        st.markdown("**Original Pre-Incident Manifest** (`512Mi` limit causing OOM)")
        base_manifest_path = os.path.join("config", "policies", f"{culprit}-deployment.yaml")
        original_manifest_text = ""
        if os.path.exists(base_manifest_path):
            with open(base_manifest_path, "r", encoding="utf-8") as f:
                original_manifest_text = f.read()
        st.code(original_manifest_text or "# Original manifest not found", language="yaml")

    with diff_col2:
        st.markdown("**Audited & Patched Manifest** (`2Gi` limit with FinOps guardrails)")
        st.code(rem_state.patch.updated_manifest or "# Patched manifest", language="yaml")

    st.markdown("**Unified Unified Diff:**")
    st.code(rem_state.patch.diff_content, language="diff")
    st.info(f"💡 **Agent Reasoning:** {rem_state.patch.reasoning}")


# -----------------------------------------------------------------------------
# Section 4: Live Sandbox Tester for Viva / Evaluators
# -----------------------------------------------------------------------------
st.divider()
st.subheader("🧪 Live Kubernetes Sandbox Policy Tester")
st.caption("Test the deterministic policy validator against custom or candidate manifests.")

sample_candidate = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-service
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: checkout-service
  template:
    metadata:
      labels:
        app: checkout-service
    spec:
      containers:
        - name: checkout-api
          image: ghcr.io/org/checkout-service:v2.4.1
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "1000m"
"""

custom_manifest_input = st.text_area(
    "Edit Kubernetes YAML to test policy sandbox:",
    value=sample_candidate,
    height=240,
)

if st.button("Run Policy Linter Sandbox"):
    validator = KubernetesSandboxValidator()
    result = validator.validate_manifest(custom_manifest_input)

    if result.is_valid:
        st.success("✅ Manifest PASSED: All FinOps & Security constraints satisfied.")
    else:
        st.error(f"❌ Manifest FAILED Validation (Errors: {len(result.linter_errors)}, Violations: {len(result.policy_violations)})")
        for err in result.linter_errors:
            st.error(f"• Linter Error: {err}")
        for viol in result.policy_violations:
            st.warning(f"• Policy Violation: {viol}")
