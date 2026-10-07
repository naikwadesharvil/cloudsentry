# PROJECT SYNOPSIS

## CloudSentry: Autonomous Multi-Agent FinOps & Distributed Cloud Incident Remediation Control Plane

---

### 1. Project Information & Metadata
- **Project Title:** CloudSentry: Autonomous Multi-Agent FinOps & Distributed Cloud Incident Remediation Control Plane
- **Academic Stream:** Bachelor of Engineering / Technology in Computer Science & Engineering (Distributed Systems & AI/ML)
- **Domain Classification:** Autonomous Systems (AIOps), Cloud FinOps, Site Reliability Engineering (SRE), Multi-Agent Control Planes
- **Industry Reference Code:** CS-AIOPS-2026-FOP
- **Keywords:** Multi-Agent Systems, LangGraph, Isolation Forest, Deterministic Sandboxing, FinOps, Kubernetes Governance, Self-Correction Loops

---

### 2. Industry Background & Problem Statement

Modern enterprise cloud infrastructure operates on complex microservices running atop container orchestrators such as Kubernetes. In production, these distributed systems face two critical operational bottlenecks:

1. **Mean Time to Resolution (MTTR) Latency & Alert Fatigue:** Traditional Application Performance Monitoring (APM) tools (e.g., Datadog, Prometheus, Dynatrace) excel at firing threshold alerts but fail at autonomous remediation. Human on-call Site Reliability Engineers (SREs) experience alert fatigue and require an average of **45 to 90 minutes** to manually ingest telemetry, correlate distributed traces, isolate root causes, and deploy infrastructure patches.
2. **Generative AI Hallucination & Financial Risks in Production:** While Large Language Models (LLMs) offer strong code synthesis capabilities, deploying unconstrained LLMs into production control planes introduces severe failure risks:
   - **Syntax & Schema Invalidation:** Emitting malformed YAML manifests or deprecated Kubernetes API schemas.
   - **FinOps Budget Overruns:** Allocating unbounded memory/CPU limits or excessive horizontal replicas, causing exponential cloud billing spikes.
   - **Noisy Neighbor Starvation:** Removing cgroup resource limits, inducing host node resource exhaustion and kernel Out-Of-Memory (OOM) cascade kills.

**CloudSentry** bridges this divide by engineering a closed-loop autonomous control plane that combines statistical multivariate anomaly detection with a cyclic multi-agent workflow governed by a **deterministic AST policy sandbox**.

---

### 3. Research Objectives & System Scope

The primary objectives of the CloudSentry platform are:
- **Autonomous Anomaly Isolation:** Ingest real-time distributed telemetry (CPU, memory, P99 latency, error rate) and reliably detect emerging failure patterns (memory leaks, CPU saturation, billing breaches) prior to full cluster degradation.
- **Root Cause Isolation without Alert Cascades:** Aggregate multi-service metrics and correlate downstream 5xx errors with upstream root resource degradation to identify the exact culprit microservice.
- **Guaranteed Policy & FinOps Compliance:** Enforce a zero-tolerance policy sandbox ensuring all synthesized Kubernetes deployment patches define strict, bounded resource requests and limits before cluster application.
- **Closed-Loop Self-Correction:** Enable automated iterative feedback loops ($k \le 3$) where sandbox linter errors and policy violations are dynamically reflected back to the patch agent for real-time refinement.
- **Resilient Dual-Engine Execution:** Support online structured LLM reasoning (Gemini / Groq) with seamless, zero-latency fallback to deterministic heuristic engines under network partitions or API rate limits.

---

### 4. System Architecture & Multi-Agent State Machine

CloudSentry is designed as a directed cyclic computational graph implemented with **LangGraph `StateGraph`** and typed with strict **Pydantic v2** schema contracts.

```
                              +-------------------------+
                              | Distributed Telemetry   |
                              | Metrics Stream (Prom/APM|
                              +------------+------------+
                                           |
                                           v
                              +-------------------------+
                              |   1. Telemetry Agent    |
                              |  - Isolation Forest     |
                              |  - Rolling OLS Slope    |
                              +------------+------------+
                                           |
                                           v
                              +-------------------------+
                              |      2. RCA Agent       |
                              |  - Dual-Engine (LLM/    |
                              |    Deterministic Heur.) |
                              |  - Culprit & Mode Class.|
                              +------------+------------+
                                           |
                                           v
                              +-------------------------+ <-------------------------+
                              |     3. Patch Agent      |                           |
                              |  - Manifest Synthesis   |                           |
                              |  - Unified AST Diff Gen |                           |
                              +------------+------------+                           |
                                           |                                        | Feedback
                                           v                                        | (Violations &
                              +-------------------------+                           |  AST Linter
                              |   4. Validator Agent    |                           |  Diagnostics)
                              |  - PyYAML AST Parser    |                           |
                              |  - FinOps Policy Check  |                           |
                              +------------+------------+                           |
                                           |                                        |
                             +-------------+-------------+                          |
                             |                           |                          |
                   [Pass: 0 Violations]        [Fail: Policy Breaches & Iter <= 3]   |
                             |                           +--------------------------+
                             v
                +-------------------------+
                |     Status: REMEDIATED  |
                |  (Cluster Patch Deployed|
                +-------------------------+
```

---

### 5. Mathematical & Algorithmic Formulations

#### 5.1 Multivariate Anomaly Scoring (Isolation Forest)
Given a cluster dataset $X = \{x_1, \dots, x_n\}$ of telemetry feature vectors $x_i = (\text{CPU}_i, \text{RAM}_i, \text{Err}_i, \text{Lat}_i) \in \mathbb{R}^4$, an ensemble of $t$ isolation trees partitions the feature space recursively.

The anomaly score $s(x, n)$ for an instance $x$ over $n$ samples is given by:
$$s(x, n) = 2^{-\frac{\mathbb{E}(h(x))}{c(n)}}$$

Where:
- $h(x)$ is the path length (number of edges traversed from root to termination node) for sample $x$.
- $\mathbb{E}(h(x))$ is the expected path length across the ensemble of isolation trees.
- $c(n)$ is the average path length of unsuccessful searches in a Binary Search Tree (BST) over $n$ nodes:
$$c(n) = 2 \ln(n - 1) + 2\gamma - \frac{2(n - 1)}{n}$$
where $\gamma \approx 0.5772156649$ is Euler's constant.
- **Decision Rule:**
  - If $s(x, n) \to 1.0$: $\mathbb{E}(h(x)) \ll c(n) \implies$ Definite Anomaly.
  - If $s(x, n) < 0.5$: $\mathbb{E}(h(x)) \to c(n) \implies$ Normal Operating Profile.

#### 5.2 Monotonic Memory Leak Slope Estimation
Instantaneous threshold checks fail to identify gradual container memory leaks. CloudSentry computes the first-order regression slope $\beta_1$ over a sliding time window $W$:
$$\beta_1 = \frac{\sum_{t=1}^W (t - \bar{t})(M_t - \bar{M})}{\sum_{t=1}^W (t - \bar{t})^2}$$

Where $M_t$ is the container resident memory in Megabytes at step $t$. An `OOM_KILL` warning is generated when $\beta_1 > 15.0 \text{ MB/step}$ and total growth $\Delta M > 80\%$.

---

### 6. Quantitative Evaluation & Empirical Results

CloudSentry was evaluated against a rigorous 50-scenario quantitative benchmark matrix (`src/evaluation/benchmark.py`) spanning multiple failure modes (`OOM_KILL`, `CPU_THROTTLING`, and `FINOPS_BUDGET_BREACH`) across all monitored services.

| Benchmark Metric | Empirical Evaluated Result | Industry / Human SRE Baseline |
| :--- | :---: | :---: |
| **Total Test Scenarios** | **50 / 50** | 50 scenarios |
| **Culprit Detection Accuracy** | **96.0%** | 70.0% – 85.0% |
| **Mean Time to Resolution (MTTR)** | **2,480.2 ms (~2.48s)** | 45 – 90 minutes (Human Triage) |
| **Zero-Shot Patch Pass Rate** | **100.0%** | < 40.0% (Raw LLMs) |
| **Overall Remediation Success Rate** | **100.0%** | > 95.0% |
| **Total Safety & FinOps Violations** | **0.0% (Zero Tolerance)** | > 25.0% (Unconstrained Generative AI) |

#### Failure Mode Performance Breakdown
- **Memory Leaks (`OOM_KILL`):** 17 Scenarios | 100.0% Accuracy | Mean MTTR: 2,289.3 ms
- **Compute Starvation (`CPU_THROTTLING`):** 17 Scenarios | 88.24% Accuracy | Mean MTTR: 2,665.4 ms
- **Budget Breaches (`FINOPS_BUDGET_BREACH`):** 16 Scenarios | 100.0% Accuracy | Mean MTTR: 2,486.2 ms

---

### 7. Hardware & Software Requirements

#### Software Stack
- **Programming Language:** Python 3.10+ / 3.12+
- **Agentic Orchestration:** LangGraph 0.2+, LangChain Core
- **Data & Machine Learning:** Scikit-learn 1.4+, NumPy, Pandas
- **Validation & Sandboxing:** PyYAML, Pydantic v2, Python `difflib`
- **User Interface & Visualizations:** Streamlit 1.30+, Plotly Express
- **LLM Integrations:** Google Gemini 2.5 Flash (`langchain-google-genai`), Groq LLaMA 3.3 70B (`langchain-groq`)

#### Hardware Environment
- **CPU:** Quad-Core x86_64 / ARM64 processor (2.0 GHz or higher)
- **RAM:** Minimum 4 GB RAM (8 GB recommended for concurrent Streamlit UI + evaluation runs)
- **Storage:** 500 MB free disk space
- **Operating System:** Cross-platform (Windows 10/11, macOS, Ubuntu Linux 22.04+)

---
*Submitted in partial fulfillment of academic requirements for final-year project examination.*
