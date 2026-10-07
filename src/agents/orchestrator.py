"""CloudSentry Orchestrator.

Wires the multi-agent incident remediation loop (Telemetry -> RCA -> Patch -> Validator)
using a LangGraph StateGraph with conditional self-correction retry loops.
"""

from typing import List, Dict, Any, Optional, Union
try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    END = "__end__"

from src.schemas.models import CloudSentryState, MetricPoint
from src.agents.telemetry_agent import run_telemetry_agent
from src.agents.rca_agent import run_rca_agent
from src.agents.patch_agent import run_patch_agent
from src.agents.validator_agent import run_validator_agent


def build_langgraph_workflow():
    """Constructs the LangGraph StateGraph for CloudSentry incident remediation."""
    if not LANGGRAPH_AVAILABLE:
        return None

    # Define StateGraph with CloudSentryState schema
    workflow = StateGraph(CloudSentryState)

    # Add agent nodes
    workflow.add_node("telemetry_agent", run_telemetry_agent)
    workflow.add_node("rca_agent", run_rca_agent)
    workflow.add_node("patch_agent", run_patch_agent)
    workflow.add_node("validator_agent", run_validator_agent)

    # Set entry point
    workflow.set_entry_point("telemetry_agent")

    # Sequential edges
    workflow.add_edge("telemetry_agent", "rca_agent")
    workflow.add_edge("rca_agent", "patch_agent")
    workflow.add_edge("patch_agent", "validator_agent")

    # Conditional router from validator_agent
    def route_after_validation(state: CloudSentryState) -> str:
        if state.status == "REMEDIATED":
            return END
        elif state.status == "FAILED":
            return END
        elif state.status == "PATCHING":
            return "patch_agent"
        return END

    workflow.add_conditional_edges(
        "validator_agent",
        route_after_validation,
        {
            END: END,
            "patch_agent": "patch_agent",
        },
    )

    return workflow.compile()


class CloudSentryOrchestrator:
    """Master orchestrator executing the full incident remediation workflow."""

    def __init__(self, use_langgraph: bool = True):
        self.use_langgraph = use_langgraph and LANGGRAPH_AVAILABLE
        self.graph = build_langgraph_workflow() if self.use_langgraph else None

    def run(self, metrics: List[MetricPoint], max_iterations: int = 5) -> CloudSentryState:
        """Executes the autonomous remediation pipeline on input telemetry metrics."""
        initial_state = CloudSentryState(
            metrics=metrics,
            status="INGESTING",
        )
        initial_state.log("[Orchestrator] Starting CloudSentry Autonomous Remediation Pipeline.")

        # If compiled LangGraph is available, run through the compiled DAG
        if self.graph is not None:
            try:
                result = self.graph.invoke(initial_state)
                if isinstance(result, CloudSentryState):
                    return result
                elif isinstance(result, dict):
                    return CloudSentryState.model_validate(result)
            except Exception as e:
                initial_state.log(f"[Orchestrator] LangGraph execution fallback triggered: {e}")

        # Deterministic State Machine Execution fallback / native loop
        state = initial_state
        state = run_telemetry_agent(state)

        # If no anomalies detected, finish early
        has_anomalies = any(a.anomaly_detected for a in state.anomalies)
        if not has_anomalies:
            state.status = "REMEDIATED"
            state.log("[Orchestrator] No anomalies detected. System healthy.")
            return state

        state = run_rca_agent(state)

        loop_count = 0
        while loop_count < max_iterations:
            loop_count += 1
            state = run_patch_agent(state)
            state = run_validator_agent(state)

            if state.status in ["REMEDIATED", "FAILED"]:
                break

        state.log(
            f"[Orchestrator] Pipeline finished with final status: '{state.status}' after {state.iteration_count} iteration(s)."
        )
        return state


def run_incident_remediation(
    metrics: List[MetricPoint], use_langgraph: bool = True
) -> CloudSentryState:
    """High-level API entrypoint for running an autonomous CloudSentry remediation loop."""
    orchestrator = CloudSentryOrchestrator(use_langgraph=use_langgraph)
    return orchestrator.run(metrics)
