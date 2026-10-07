"""CloudSentry Live Incident Triage & Autonomous Remediation Dashboard.

Interactive Streamlit operations console for visualizing distributed microservice telemetry,
triggering simulated incident outages across microservices and failure scenarios,
filtering telemetry streams across services, deep-diving into individual service architectures,
observing multi-agent DAG execution traces, and inspecting FinOps Kubernetes YAML remediation diffs.
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

from src.schemas.models import CloudSentryState, MetricPoint, AnomalyReport
from src.tools.metric_generator import MetricGenerator
from src.tools.anomaly_detector import MetricAnomalyDetector
from src.tools.k8s_sandbox import KubernetesSandboxValidator
from src.tools.llm_provider import get_api_key_provider, is_llm_available
from src.agents.telemetry_agent import run_telemetry_agent
from src.agents.rca_agent import run_rca_agent
from src.agents.patch_agent import PatchAgent, run_patch_agent
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
        margin-bottom: 20px;
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
    
    /* Inspector metric container */
    .inspector-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

ALL_SERVICES = ["checkout-service", "auth-service", "payment-service", "inventory-service"]
FAILURE_SCENARIOS = ["OOM_KILL", "CPU_THROTTLING", "FINOPS_BUDGET_BREACH"]

# -----------------------------------------------------------------------------
# State Management Initialization
# -----------------------------------------------------------------------------
if "incident_active" not in st.session_state:
    st.session_state.incident_active = False

if "remediation_state" not in st.session_state:
    st.session_state.remediation_state = None

if "target_microservice" not in st.session_state:
    st.session_state.target_microservice = "checkout-service"

if "failure_scenario" not in st.session_state:
    st.session_state.failure_scenario = "OOM_KILL"

if "telemetry_metrics" not in st.session_state:
    gen = MetricGenerator(random_seed=42)
    st.session_state.telemetry_metrics = gen.generate_cluster_telemetry(
        culprit_service=st.session_state.target_microservice,
        culprit_scenario=st.session_state.failure_scenario,
        num_steps=20,
    )


# -----------------------------------------------------------------------------
# Sidebar Configuration: Incident Target Controls
# -----------------------------------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/shield.png", width=64)
    st.title("CloudSentry Engine")
    st.caption("Autonomous Incident Remediation & FinOps Guardrails")
    st.divider()

    st.subheader("🎯 Incident Simulation Controls")

    target_microservice = st.sidebar.selectbox(
        "Target Microservice",
        options=ALL_SERVICES,
        index=ALL_SERVICES.index(st.session_state.target_microservice)
        if st.session_state.target_microservice in ALL_SERVICES
        else 0,
        help="Select the microservice to inject with the simulated failure scenario.",
    )

    failure_scenario = st.sidebar.selectbox(
        "Failure Scenario",
        options=FAILURE_SCENARIOS,
        index=FAILURE_SCENARIOS.index(st.session_state.failure_scenario)
        if st.session_state.failure_scenario in FAILURE_SCENARIOS
        else 0,
        help="Simulate distinct distributed failure signatures across cluster workloads.",
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
        trigger_btn = st.button("🚨 Run Remediation", use_container_width=True, type="primary")
    with col_btn2:
        reset_btn = st.button("🔄 Reset Telemetry", use_container_width=True)

    if reset_btn:
        st.session_state.incident_active = False
        st.session_state.remediation_state = None
        st.session_state.target_microservice = target_microservice
        st.session_state.failure_scenario = failure_scenario
        gen = MetricGenerator(random_seed=42)
        st.session_state.telemetry_metrics = gen.generate_cluster_telemetry(
            culprit_service=target_microservice,
            culprit_scenario="HEALTHY",
            num_steps=simulation_steps,
        )
        st.rerun()

    if trigger_btn:
        st.session_state.incident_active = True
        st.session_state.target_microservice = target_microservice
        st.session_state.failure_scenario = failure_scenario
        gen = MetricGenerator(random_seed=42)
        st.session_state.telemetry_metrics = gen.generate_cluster_telemetry(
            culprit_service=target_microservice,
            culprit_scenario=failure_scenario,
            num_steps=simulation_steps,
        )
        # Execute Orchestrator
        orchestrator = CloudSentryOrchestrator(use_langgraph=True)
        st.session_state.remediation_state = orchestrator.run(
            st.session_state.telemetry_metrics
        )
        st.rerun()


# -----------------------------------------------------------------------------
# Header
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


# -----------------------------------------------------------------------------
# Section 1: Telemetry Multi-Service View & Filter
# -----------------------------------------------------------------------------
st.subheader("📊 Live Distributed Microservice Telemetry Stream")

selected_services = st.multiselect(
    "Filter Active Services to Display",
    options=ALL_SERVICES,
    default=ALL_SERVICES,
    help="Isolate individual microservices or observe aggregate cluster dynamics across all services.",
)

# Service Health Status Cards (Filtered)
rem_state = st.session_state.remediation_state
culprit = (
    rem_state.rca.culprit_service
    if (rem_state and rem_state.rca)
    else st.session_state.target_microservice
)
is_remediated = rem_state is not None and rem_state.status == "REMEDIATED"

if selected_services:
    health_cols = st.columns(len(selected_services))
    for idx, svc in enumerate(selected_services):
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
                    <div style="font-size: 1.1rem; font-weight: 600; color: #f0f6fc; margin-bottom: 6px;">
                        {health_icon} {svc}
                    </div>
                    <span class="status-badge {badge_class}">{status_label}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
else:
    st.info("ℹ️ No microservices selected. Use the filter above to select active services.")

st.write("")

# Render 4-Panel Plotly Subplots (Filtered)
metrics_df = pd.DataFrame([m.model_dump() for m in st.session_state.telemetry_metrics])

if not selected_services or metrics_df.empty:
    st.warning("⚠️ No telemetry to display for the current filter selection.")
else:
    filtered_df = metrics_df[metrics_df["service_name"].isin(selected_services)]

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

    for svc in selected_services:
        svc_data = filtered_df[filtered_df["service_name"] == svc].sort_values("timestamp")
        if svc_data.empty:
            continue
        color = color_map.get(svc, "#8b949e")
        is_target = svc == culprit and st.session_state.incident_active

        # 1. Memory
        fig.add_trace(
            go.Scatter(
                x=svc_data["timestamp"],
                y=svc_data["memory_usage_mb"],
                name=svc,
                legendgroup=svc,
                line=dict(color=color, width=2.8 if is_target else 1.5),
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
                line=dict(color=color, width=2.8 if is_target else 1.5),
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
                line=dict(color=color, width=2.8 if is_target else 1.5),
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
                line=dict(color=color, width=2.8 if is_target else 1.5),
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

    st.plotly_chart(fig, use_container_width=True)


# -----------------------------------------------------------------------------
# Section 2: Service Detail Inspector
# -----------------------------------------------------------------------------
st.divider()
st.subheader("🔬 Service Detail Inspector")
st.caption("Deep-dive inspection of baseline resource allocations, anomaly telemetry flags, and Kubernetes deployment specifications.")

with st.expander("🔎 Open Microservice Architecture & Manifest Inspector", expanded=True):
    insp_col_select, insp_col_spacer = st.columns([1, 2])
    with insp_col_select:
        inspected_service = st.selectbox(
            "Select Service to Inspect",
            options=ALL_SERVICES,
            index=0,
            key="inspector_service_dropdown",
        )

    # Load Service Kubernetes Manifest
    patch_agent_helper = PatchAgent()
    manifest_path, manifest_dict, manifest_yaml = patch_agent_helper._load_base_manifest(inspected_service)

    # Extract container spec details
    containers = manifest_dict.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    first_container = containers[0] if containers else {}
    res_req = first_container.get("resources", {}).get("requests", {})
    res_lim = first_container.get("resources", {}).get("limits", {})
    replicas = manifest_dict.get("spec", {}).get("replicas", 3)
    image_name = first_container.get("image", f"ghcr.io/org/{inspected_service}:latest")

    # Compute telemetry aggregates for inspected service
    svc_telemetry = [m for m in st.session_state.telemetry_metrics if m.service_name == inspected_service]
    if svc_telemetry:
        df_svc = pd.DataFrame([m.model_dump() for m in svc_telemetry])
        peak_mem = df_svc["memory_usage_mb"].max()
        avg_mem = df_svc["memory_usage_mb"].mean()
        peak_cpu = df_svc["cpu_usage_pct"].max()
        avg_cpu = df_svc["cpu_usage_pct"].mean()
        peak_lat = df_svc["p99_latency_ms"].max()
        peak_err = df_svc["error_rate_pct"].max()
    else:
        peak_mem = avg_mem = peak_cpu = avg_cpu = peak_lat = peak_err = 0.0

    # Compute or retrieve anomaly report
    detector = MetricAnomalyDetector()
    anomaly_rep = detector.detect_service_anomalies(inspected_service, svc_telemetry)
    if rem_state and rem_state.anomalies:
        for a in rem_state.anomalies:
            if a.service_name == inspected_service:
                anomaly_rep = a
                break

    # Inspector Layout: 3 Columns (Baseline Allocations, Anomaly Diagnostics, K8s Manifest)
    insp_c1, insp_c2 = st.columns([1, 1])

    with insp_c1:
        st.markdown("##### ⚙️ Baseline Resource Allocations")
        m_c1, m_c2, m_c3 = st.columns(3)
        with m_c1:
            st.metric("Memory Limit", res_lim.get("memory", "512Mi"), f"Req: {res_req.get('memory', '256Mi')}")
        with m_c2:
            st.metric("CPU Limit", res_lim.get("cpu", "500m"), f"Req: {res_req.get('cpu', '200m')}")
        with m_c3:
            st.metric("Replicas", f"{replicas} pods", f"Image: {image_name.split(':')[-1]}")

        st.markdown("##### 📈 Live Telemetry Statistics")
        t_c1, t_c2, t_c3 = st.columns(3)
        with t_c1:
            st.metric("Peak Memory", f"{peak_mem:.1f} MB", f"Avg: {avg_mem:.1f} MB")
        with t_c2:
            st.metric("Peak CPU", f"{peak_cpu:.1f} %", f"Avg: {avg_cpu:.1f} %")
        with t_c3:
            st.metric("Peak P99 Latency", f"{peak_lat:.1f} ms", f"Max Err: {peak_err:.2f}%")

        st.markdown("##### 🛡️ Anomaly Telemetry Flags")
        if anomaly_rep.anomaly_detected:
            sev_color = "#f85149" if anomaly_rep.severity in ["CRITICAL", "HIGH"] else "#d29922"
            st.error(f"🚨 **{anomaly_rep.severity} ANOMALY FLAGGED** (Trigger: `{anomaly_rep.trigger_metric}`)")
            st.markdown(f"**Diagnostic Summary:** {anomaly_rep.summary}")
            if anomaly_rep.anomaly_score is not None:
                st.caption(f"Isolation Forest Outlier Score: `{anomaly_rep.anomaly_score:.4f}`")
        else:
            st.success(f"✅ **NOMINAL HEALTH**: {anomaly_rep.summary}")

    with insp_c2:
        st.markdown(f"##### 📄 Kubernetes Deployment Spec (`{os.path.basename(manifest_path)}`)")
        if rem_state and rem_state.patch and inspected_service == culprit:
            tab1, tab2, tab3 = st.tabs(["Audited & Patched Spec", "Baseline Spec", "Unified Diff"])
            with tab1:
                st.code(rem_state.patch.updated_manifest, language="yaml")
            with tab2:
                st.code(manifest_yaml, language="yaml")
            with tab3:
                st.code(rem_state.patch.diff_content, language="diff")
        else:
            st.code(manifest_yaml, language="yaml")


# -----------------------------------------------------------------------------
# Section 3: Agent DAG Execution Trace
# -----------------------------------------------------------------------------
if rem_state:
    st.divider()
    st.subheader("⚡ Multi-Agent Incident Remediation Trace")

    trace_cols = st.columns(4)

    # 1. Telemetry Node
    with trace_cols[0]:
        anomalies_flagged = [a for a in rem_state.anomalies if a.anomaly_detected]
        node_status_class = "dag-node-alert" if anomalies_flagged else "dag-node-success"
        trigger_text = anomalies_flagged[0].trigger_metric if anomalies_flagged else "None"
        severity_text = anomalies_flagged[0].severity if anomalies_flagged else "NOMINAL"
        st.markdown(
            f"""
            <div class="dag-node {node_status_class}">
                <div style="font-weight:700; color:#58a6ff; margin-bottom:4px;">1. Telemetry Agent</div>
                <div style="font-size:0.85rem; color:#f0f6fc;">
                    Flagged: <b>{len(anomalies_flagged)} anomaly</b><br/>
                    Trigger: <span style="color:#f85149;">{trigger_text}</span><br/>
                    Severity: <b>{severity_text}</b>
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
# Section 4: Unified Diff & Corrected Kubernetes Manifest
# -----------------------------------------------------------------------------
if rem_state and rem_state.patch:
    st.divider()
    st.subheader("🔍 FinOps Remediation: Manifest Diff & Corrected Manifest")

    diff_col1, diff_col2 = st.columns(2)

    with diff_col1:
        st.markdown(f"**Original Pre-Incident Manifest** (`{culprit}`)")
        base_manifest_path = os.path.join("config", "policies", f"{culprit}-deployment.yaml")
        original_manifest_text = ""
        if os.path.exists(base_manifest_path):
            with open(base_manifest_path, "r", encoding="utf-8") as f:
                original_manifest_text = f.read()
        else:
            _, _, original_manifest_text = PatchAgent()._load_base_manifest(culprit)
        st.code(original_manifest_text or "# Original manifest not found", language="yaml")

    with diff_col2:
        st.markdown(f"**Audited & Patched Manifest** (`{culprit}` with FinOps guardrails)")
        st.code(rem_state.patch.updated_manifest or "# Patched manifest", language="yaml")

    st.markdown("**Unified Diff:**")
    st.code(rem_state.patch.diff_content, language="diff")
    st.info(f"💡 **Agent Reasoning:** {rem_state.patch.reasoning}")


# -----------------------------------------------------------------------------
# Section 5: Live Sandbox Policy Tester
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
