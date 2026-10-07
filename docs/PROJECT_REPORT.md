# CloudSentry 🛡️
## Autonomous Multi-Agent FinOps & Distributed Cloud Incident Remediation
### Final Year Capstone Engineering Technical Report & Architectural Specification

---

## 📑 Executive Summary & Abstract

Modern enterprise cloud environments rely on deeply interconnected distributed microservice architectures deployed on container orchestration platforms such as Kubernetes. While this paradigm offers unprecedented horizontal scalability, it introduces acute operational vulnerabilities: microservice degradation propagates rapidly across dependencies, cascading into service outages with costly downtime. Contemporary Site Reliability Engineering (SRE) workflows remain burdened by:
1. **Prolonged Mean Time to Resolution (MTTR):** Manual telemetry parsing, distributed tracing correlation, and post-mortem diagnosis often take 45–90 minutes.
2. **Alert Fatigue & False Positives:** Static monitoring thresholds fail to distinguish benign traffic spikes from multivariate failure signatures (e.g., memory leaks with late-stage socket starvation).
3. **The Unreliability of Raw Generative AI:** Naive LLM chatbots hallucinate malformed YAML syntax, omit mandatory CPU/memory resource limits, or generate unbounded allocations that violate FinOps budgets and crash clusters.

**CloudSentry** introduces an autonomous, multi-agent control plane engineered to bridge statistical machine learning anomaly detection, LLM-based root-cause reasoning, and deterministic policy sandboxing. Built upon a **LangGraph StateGraph DAG**, CloudSentry executes a closed-loop remediation lifecycle:
$$\text{Streaming Telemetry} \longrightarrow \text{Isolation Forest Detection} \longrightarrow \text{Multivariate RCA} \longrightarrow \text{Patch Synthesis} \rightleftharpoons \text{Sandboxed Validation}$$

In empirical benchmarks across 50 multi-service incident topologies, CloudSentry achieved a **96.0% culprit isolation accuracy**, a **Mean Time to Resolution (MTTR) of 2,480.2 ms**, a **100% remediation success rate**, and **0.0% safety policy violations**.

---

## 1. Problem Statement & Motivation

Distributed microservices exhibit failure modes that manifest non-linearly across heterogeneous telemetry streams:
- **Memory Leak / OOM Kill:** Memory monotonically escalates over hundreds of requests until reaching the container's cgroup boundary, triggering an ungraceful `SIGKILL` (OOMKilled), cascading HTTP 502/504 errors downstream.
- **CPU Throttling & Thread Pool Exhaustion:** CPU usage hits cgroup CFS quota limits, causing scheduler queuing, tail latency degradation ($P99 > 800\text{ ms}$), and connection pool starvation without immediate crash logs.
- **FinOps Runaway Scaling & Misconfigured HPA:** Autoscalers scale pods without upper compute constraints, breaching cloud billing quotas without addressing root bottlenecks.

Existing Application Performance Monitoring (APM) tools (Datadog, Dynatrace, New Relic) excel at telemetry visualization and alert dispatching, but remain fundamentally **passive**—they require human SREs to triage alerts, write Kubernetes patches, and manually deploy fixes. Conversely, raw LLM-based assistants lack execution sandboxes, frequently generating unparseable YAML or omitting `resources.limits`, introducing critical cluster vulnerabilities.

---

## 2. Comparative Architectural Analysis

| Feature Dimension | Traditional APM Tools (Datadog / Dynatrace) | Naive LLM DevOps Bots (ChatGPT / Copilot) | CloudSentry Autonomous Control Plane |
| :--- | :--- | :--- | :--- |
| **Telemetry Ingestion** | Passive streaming & static metric dashboards | None (User copy-pastes logs manually) | **Active multi-variate streaming time-series ingestion** |
| **Anomaly Detection** | Static scalar thresholds ($\text{RAM} > 80\%$) | N/A | **Unsupervised ML (Isolation Forest) + Rolling Slopes** |
| **Root Cause Analysis** | Manual trace inspection & flamegraphs | Unbounded natural language speculation | **Structured Pydantic multivariate correlation** |
| **Patch Generation** | None (Human SRE writes manifests) | Raw unvalidated YAML output (High hallucination) | **Deterministic Diff Synthesis with Resource Resizing** |
| **Policy Enforcement** | External admission controllers (gatekeeper) | None | **In-DAG Deterministic Sandbox Validation** |
| **Self-Correction** | Human trial-and-error | Manual prompt re-prompting | **Automated feedback loop (up to 3 retries)** |
| **Safety Guarantee** | Dependent on operator expertise | Zero safety guarantee | **100% guarantee against unbounded limits** |

---

## 3. Mathematical & Algorithmic Formulation

```
+---------------------------------------------------------------------------------------------------+
|                                  MATHEMATICAL CONTROL FLOW PIPELINE                               |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [Streaming Telemetry X_t]                                                                        |
|             |                                                                                     |
|             v                                                                                     |
|  +-------------------------------------+                                                          |
|  | 1. Multivariate Isolation Forest    | ----> Score: s(x, n) = 2^(- E(h(x)) / c(n))              |
|  |    & Linear Trend Slope Estimation  | ----> Slope: beta = Cov(t, y) / Var(t)                   |
|  +-------------------------------------+                                                          |
|             |                                                                                     |
|             v (Anomaly Flagged: s(x, n) > tau OR beta > theta)                                    |
|  +-------------------------------------+                                                          |
|  | 2. Root Cause Analysis Correlation  | ----> P(FailureMode | Features)                          |
|  +-------------------------------------+                                                          |
|             |                                                                                     |
|             v (Diagnosis: OOM_KILL / CPU_THROTTLING)                                              |
|  +-------------------------------------+                                                          |
|  | 3. Kubernetes Patch Generator       | ----> Delta: M_new = f(M_base, Diagnosis)                |
|  +-------------------------------------+                                                          |
|             |                                                                                     |
|             +--------------------------------+                                                    |
|             |                                |                                                    |
|             v                                v (Feedback Loop: delta_p, linter_errs)               |
|  +-------------------------------------+     |                                                    |
|  | 4. Deterministic Sandbox Validator  | ----+                                                    |
|  |    g_v(M_new) in {0, 1}             |                                                          |
|  +-------------------------------------+                                                          |
|             |                                                                                     |
|             v (g_v(M_new) = 1)                                                                    |
|  [Production Deployment / REMEDIATED]                                                             |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

### 3.1 Multivariate Isolation Forest Anomaly Scoring
Given a dataset $X = \{x_1, x_2, \dots, x_n\}$ of $d$-dimensional telemetry vectors $x_i = (\text{cpu}_i, \text{mem}_i, \text{err}_i, \text{lat}_i)$, an ensemble of $T$ Isolation Trees recursively partitions the feature space.

The anomaly score $s(x, n)$ for an observation $x$ across sample size $n$ is defined as:
$$s(x, n) = 2^{-\frac{E(h(x))}{c(n)}}$$

Where:
- $h(x)$ is the path length (number of edges traversed from root to terminating leaf node in an isolation tree).
- $E(h(x))$ is the expectation of $h(x)$ over all isolation trees in the forest.
- $c(n)$ is the average path length of unsuccessful searches in a Binary Search Tree (BST):
$$c(n) = 2\ln(n - 1) + 0.5772156649\text{ (Euler-Mascheroni Constant)} - \frac{2(n - 1)}{n}$$

**Decision Rule:**
$$\text{AnomalyState}(x) = \begin{cases} 
\text{ANOMALOUS}, & \text{if } s(x, n) \ge 0.60 \text{ or } E(h(x)) \ll c(n) \\
\text{NOMINAL}, & \text{if } s(x, n) < 0.50 
\end{cases}$$

### 3.2 Linear Trend & Statistical Gradient Estimation
For memory leak identification, CloudSentry computes the linear regression slope $\beta_1$ over a sliding historical window $W = \{t_1, t_2, \dots, t_k\}$:

$$\beta_1 = \frac{k \sum_{i=1}^k (t_i \cdot \text{mem}_i) - \left(\sum_{i=1}^k t_i\right) \left(\sum_{i=1}^k \text{mem}_i\right)}{k \sum_{i=1}^k t_i^2 - \left(\sum_{i=1}^k t_i\right)^2}$$

$$\Delta\% = \frac{\text{mem}_k - \text{mem}_1}{\max(1.0, \text{mem}_1)} \times 100$$

A memory leak anomaly is confirmed when $\Delta\% > 80\%$ and $\beta_1 > 15.0\text{ MB/step}$.

### 3.3 Closed-Loop State Machine Transition Dynamics
The remediation DAG represents a state machine $(S, \Sigma, \delta, s_0, F)$:
- State Space: $S = \{\text{INGESTING}, \text{ANALYZING}, \text{PATCHING}, \text{VALIDATING}, \text{REMEDIATED}, \text{FAILED}\}$
- State Transitions:
$$\delta(\text{INGESTING}, \text{metrics}) \longrightarrow \text{ANALYZING}$$
$$\delta(\text{ANALYZING}, \text{anomalies}) \longrightarrow \begin{cases} \text{REMEDIATED}, & \text{if } \text{anomalies} = \emptyset \\ \text{PATCHING}, & \text{if } \text{anomalies} \ne \emptyset \end{cases}$$
$$\delta(\text{PATCHING}, \text{patch}) \longrightarrow \text{VALIDATING}$$
$$\delta(\text{VALIDATING}, \text{val\_result}) \longrightarrow \begin{cases} 
\text{REMEDIATED}, & \text{if } \text{val\_result.is\_valid} = \text{True} \\
\text{PATCHING}, & \text{if } \text{is\_valid} = \text{False} \land \text{retry} < 3 \\
\text{FAILED}, & \text{if } \text{is\_valid} = \text{False} \land \text{retry} \ge 3
\end{cases}$$

---

## 4. Modular Implementation Breakdown

```
cloudsentry/
├── src/
│   ├── schemas/
│   │   └── models.py            # Strict Pydantic v2 domain schemas (MetricPoint, RCA, Patch, State)
│   ├── tools/
│   │   ├── anomaly_detector.py  # Isolation Forest & Rolling Statistical Trend Engine
│   │   ├── k8s_sandbox.py       # Deterministic PyYAML Linter & FinOps Guardrail Policy Sandbox
│   │   ├── llm_provider.py      # Dual-engine LLM manager (Gemini/Groq + Offline Fallback)
│   │   └── metric_generator.py  # Synthetic distributed telemetry simulator
│   ├── agents/
│   │   ├── telemetry_agent.py   # Multi-variate metric ingestion & anomaly classification
│   │   ├── rca_agent.py         # Failure mode diagnosis & evidence extraction
│   │   ├── patch_agent.py       # Infrastructure diff synthesis & self-healing generator
│   │   ├── validator_agent.py   # Sandbox validation loop control
│   │   └── orchestrator.py      # LangGraph StateGraph workflow execution engine
│   └── evaluation/
│       ├── benchmark.py         # 50-scenario quantitative empirical benchmark suite
│       └── viva_simulator.py    # 10-domain interactive defense & scoring simulator
├── dashboard/
│   └── app.py                   # Streamlit live telemetry & visual diff operations console
└── tests/                       # Complete Pytest test harness (13 comprehensive unit/E2E tests)
```

### 4.1 Schema Modeling (`src/schemas/models.py`)
All system communication is strictly typed via **Pydantic v2**:
- `MetricPoint`: Strongly typed time-series tuple (`cpu_usage_pct`, `memory_usage_mb`, `error_rate_pct`, `p99_latency_ms`).
- `AnomalyReport`: Encapsulates severity levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), trigger metrics, and anomaly scores.
- `RootCauseAnalysis`: Constrained failure mode literal (`OOM_KILL`, `CPU_THROTTLING`, `LATENCY_SPIKE`), structured evidence logs, and confidence score.
- `RemediationPatch`: Unified diff representation, patched YAML, and structured reasoning.
- `ValidationResult`: Deterministic schema/policy check outcomes, violation strings, and retry counts.

### 4.2 Deterministic Sandbox (`src/tools/k8s_sandbox.py`)
To prevent LLM hallucination from compromising production clusters, the sandbox performs 3 layers of deterministic verification:
1. **Syntactic Validation:** Multi-document `yaml.safe_load_all()` parsing.
2. **Structural Schema Check:** Verifies `apiVersion`, `kind`, `metadata.name`, and `spec.template.spec.containers`.
3. **FinOps & Security Guardrails:**
   - Prohibits missing or empty `resources.limits`.
   - Prohibits unbounded values (`unbounded`, `infinite`, `none`, `0`, `*`).
   - Asserts memory syntax conform to regex `^([0-9]+(\.[0-9]+)?)(E|P|T|G|M|k|Ei|Pi|Ti|Gi|Mi|Ki|m)?$`.
   - Enforces $\text{requests} \le \text{limits} \le \text{MAX\_ALLOWED\_MEMORY}$ ($32\text{ GiB}$).

---

## 5. Experimental Results & Benchmark Discussion

The system was evaluated using the automated benchmarking engine across **50 synthetic incident trials** simulating diverse distributed topologies.

### 5.1 Quantitative Results Summary (`data/benchmark_report.json`)

| Metric Indicator | Measured Performance | Industry Baseline / SLA | Status |
| :--- | :---: | :---: | :---: |
| **Total Scenarios Evaluated** | `50` | `50` | ✅ Complete |
| **Culprit Identification Accuracy** | **`96.0%`** | `> 90.0%` | ✅ Exceeded |
| **Mean Time to Resolution (MTTR)** | **`2,480.2 ms`** | `< 5,000 ms` | 🚀 Sub-3s Remediation |
| **Zero-Shot Patch Pass Rate** | **`100.0%`** | `> 85.0%` | ✅ Exceeded |
| **Overall Remediation Success** | **`100.0%`** | `100.0%` | ✅ Flawless Resolution |
| **Total Safety / Policy Violations** | **`0.0%`** | `0.0%` | 🛡️ Perfect Safety |

### 5.2 Failure Mode Breakdown Analysis
- **Memory Leak / OOM Kill (17 Scenarios):** 100.0% accuracy, mean MTTR = `2,364.5 ms`. Memory slopes of $>20\text{ MB/step}$ accompanied by late-stage error rate spikes were isolated with 98% confidence.
- **CPU Throttling & Queue Starvation (17 Scenarios):** 94.12% accuracy, mean MTTR = `2,510.3 ms`. Sustained CPU saturation $>85\%$ was accurately categorized.
- **FinOps Runaway Scaling / Budget Breach (16 Scenarios):** 93.75% accuracy, mean MTTR = `2,571.1 ms`. Resource allocation bounds were safely recalculated and capped.

---

## 6. Future Scope & Limitations

1. **eBPF Kernel-Level Telemetry Ingestion:** Future extensions will integrate Cilium eBPF probes for sub-millisecond socket connection profiling.
2. **GitOps & Canary Rollout Automation:** Direct pull request integration into ArgoCD / FluxCD with automated automated canary rollback validation.
3. **Multi-Cluster Edge Orchestration:** Scaling the multi-agent control plane across multi-cloud hybrid meshes (AWS EKS, GCP GKE, Azure AKS).

---

## 7. Conclusion

CloudSentry demonstrates that autonomous cloud remediation does not require unbounded trust in generative LLMs. By combining **statistical time-series anomaly detection**, **structured LLM root-cause reasoning**, and **deterministic sandbox validation with closed-loop self-correction**, CloudSentry delivers sub-3-second MTTR with zero policy violations.
