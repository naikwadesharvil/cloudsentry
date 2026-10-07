"""CloudSentry Interactive Viva & Technical Defense Simulator.

Provides an automated evaluation environment for practicing defense questions
across Theoretical ML, LangGraph Multi-Agent Orchestration, Sandboxed Kubernetes Security,
and Production Distributed Systems Engineering.
"""

import sys
import os
import argparse
import time

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


VIVA_QUESTIONS = [
    {
        "id": 1,
        "domain": "Theoretical ML & Anomaly Detection",
        "question": "How does the Isolation Forest algorithm isolate multivariate anomalies compared to distance-based clustering algorithms like DBSCAN or K-Means?",
        "keywords": ["subsampling", "path length", "partitions", "linear", "random split", "hyperplane", "isolation", "density"],
        "model_answer": "Isolation Forest explicitly isolates anomalies rather than profiling normal data points. It recursively partitions feature space using random split values. Anomalies require fewer partitions to isolate, resulting in significantly shorter tree path lengths h(x). Unlike DBSCAN or K-Means, which have O(n^2) distance computation complexity, Isolation Forest has linear O(n) time complexity and low memory footprint.",
        "sample_response": "Isolation Forest uses random split partitions to isolate data points into binary trees. Anomalies have short path lengths h(x) near the root because they require few partitions, achieving linear O(n) complexity without expensive distance calculations.",
    },
    {
        "id": 2,
        "domain": "Theoretical ML & Anomaly Detection",
        "question": "Why is first-derivative linear slope estimation necessary alongside Isolation Forests for detecting container memory leaks?",
        "keywords": ["slope", "growth", "monotonic", "gradual", "cgroup", "trend", "derivative", "oom"],
        "model_answer": "A slow memory leak may appear statistically normal within any single time window because absolute memory usage increases gradually. Computing the linear regression slope (first derivative) over a rolling window detects the monotonic growth trajectory before the container breaches its cgroup memory limit and gets terminated by the Linux OOM-killer.",
        "sample_response": "Gradual memory leaks look normal in instantaneous snapshots. Computing the linear regression slope derivative over a rolling window detects the monotonic growth trend before the container breaches its cgroup limit and triggers an OOM kill.",
    },
    {
        "id": 3,
        "domain": "Theoretical ML & Anomaly Detection",
        "question": "In the Isolation Forest scoring formula s(x, n) = 2^(-E(h(x))/c(n)), what does the term c(n) represent and why is it used to normalize path length?",
        "keywords": ["average path length", "binary search tree", "unsuccessful", "euler", "normalization", "bst"],
        "model_answer": "c(n) represents the average path length of unsuccessful searches in a Binary Search Tree (BST) constructed over n samples, calculated as c(n) = 2*ln(n-1) + 0.5772156649 - 2*(n-1)/n. It serves as an asymptotic normalization factor so that the expected tree depth E(h(x)) is bounded, mapping the final anomaly score s(x, n) strictly between 0 and 1.",
        "sample_response": "c(n) is the average path length of unsuccessful searches in a Binary Search Tree (BST) using Euler-Mascheroni constant. It provides asymptotic normalization so tree depth E(h(x)) maps the anomaly score s(x, n) between 0 and 1.",
    },
    {
        "id": 4,
        "domain": "Multi-Agent Orchestration & LangGraph",
        "question": "Explain how CloudSentry leverages LangGraph's StateGraph to implement conditional feedback loops between the Validator Agent and the Patch Agent.",
        "keywords": ["stategraph", "conditional edges", "router", "retry", "loop", "feedback", "remediated", "failed"],
        "model_answer": "CloudSentry models the remediation workflow as a LangGraph StateGraph. The Validator Agent is connected via a conditional router edge. If the sandbox validation fails and retry_count < 3, the conditional router redirects execution back to the Patch Agent with linter error feedback. If validation passes, it routes to END with status REMEDIATED.",
        "sample_response": "CloudSentry constructs a LangGraph StateGraph where the Validator Agent has conditional edges router. If validation fails, it triggers a feedback loop back to the Patch Agent with retry count tracking, or routes to END when remediated.",
    },
    {
        "id": 5,
        "domain": "Multi-Agent Orchestration & LangGraph",
        "question": "Why are strict Pydantic v2 models preferred over generic JSON dicts for inter-agent communication in autonomous control planes?",
        "keywords": ["type safety", "validation", "pydantic", "runtime", "schema", "contract", "serialization", "guarantee"],
        "model_answer": "Pydantic v2 enforces strict runtime schema validation, static typing, and serialization guarantees. It eliminates KeyError and schema drift between asynchronous agents. Furthermore, Pydantic schemas can be directly bound to LLM structured output functions (via model.with_structured_output), guaranteeing deterministic JSON output from LLMs.",
        "sample_response": "Pydantic v2 guarantees strict type safety, schema contracts, and runtime validation. It binds directly to LLM structured outputs to prevent schema drift and ensure deterministic serialization across agents.",
    },
    {
        "id": 6,
        "domain": "Multi-Agent Orchestration & LangGraph",
        "question": "How does CloudSentry maintain high availability when external LLM APIs (e.g., Gemini or Groq) encounter 429 rate limits or timeouts?",
        "keywords": ["fallback", "deterministic", "heuristic", "resilience", "dual-engine", "offline", "graceful", "exception"],
        "model_answer": "CloudSentry implements a resilient Dual-Engine architecture. In RCAAgent and PatchAgent, LLM calls are wrapped in exception handlers. If an API key is absent, rate-limited (HTTP 429), or times out, the agent catches the error and immediately falls back to deterministic heuristic engines (polynomial slope estimation & rule-based YAML resizing) without crashing.",
        "sample_response": "CloudSentry implements a dual-engine architecture with graceful exception handling. When LLM APIs hit 429 rate limits or timeout, it automatically executes offline deterministic heuristic fallback engines.",
    },
    {
        "id": 7,
        "domain": "Policy Sandboxing & Kubernetes Guardrails",
        "question": "What security and FinOps risks arise when a Kubernetes Deployment manifest omits resources.limits or specifies 'unbounded'?",
        "keywords": ["noisy neighbor", "oom", "kernel", "starvation", "finops", "billing", "cgroup", "unbounded"],
        "model_answer": "Omitting resources.limits allows a malfunctioning container to consume all available node memory and CPU. This creates 'noisy neighbor' resource starvation for co-located workloads and can trigger the Linux kernel OOM killer to terminate critical pods. In FinOps, unbounded containers prevent cluster bin-packing and trigger runaway autoscaling bills.",
        "sample_response": "Omitting resources.limits causes noisy neighbor CPU and memory starvation across cgroups, triggering Linux kernel OOM kills. In FinOps, unbounded resources lead to runaway autoscaler billing.",
    },
    {
        "id": 8,
        "domain": "Policy Sandboxing & Kubernetes Guardrails",
        "question": "How does the KubernetesSandboxValidator deterministically verify candidate YAML manifests before production deployment?",
        "keywords": ["pyyaml", "linter", "ast", "regex", "quantities", "syntax", "limits", "deterministic"],
        "model_answer": "The sandbox uses PyYAML to parse the manifest AST. It verifies required fields (apiVersion, kind, metadata.name), inspects all container specs, applies regex checks to validate Kubernetes quantities (e.g., 512Mi, 1Gi, 1000m), rejects prohibited unbounded tokens, and verifies that requests <= limits <= MAX_ALLOWED_MEMORY.",
        "sample_response": "The sandbox uses PyYAML linter to parse AST structures, runs regex on resource quantities (Mi, Gi, m), rejects unbounded tokens, and ensures requests and limits satisfy deterministic FinOps rules.",
    },
    {
        "id": 9,
        "domain": "Production Systems & Scalability",
        "question": "In a distributed microservice cluster with hundreds of nodes, how does CloudSentry prevent alert storms and cascading remediation actions?",
        "keywords": ["correlation", "group-by", "severity", "culprit", "distributed", "dampening", "trace"],
        "model_answer": "CloudSentry performs multi-service group-by metric aggregation. The RCA Agent correlates downstream HTTP 5xx errors with upstream resource degradation (memory/CPU spikes). It ranks anomalies by severity and confidence, isolating the single root-cause culprit rather than firing remediation patches for every affected downstream client.",
        "sample_response": "CloudSentry runs distributed group-by metric aggregation and correlation. It maps downstream 5xx errors to the root resource spike, ranks anomalies by severity, and isolates the single culprit microservice to stop alert storms.",
    },
    {
        "id": 10,
        "domain": "Production Systems & Scalability",
        "question": "What is Mean Time to Resolution (MTTR), and how does CloudSentry achieve an empirical MTTR of ~2.48 seconds in benchmark evaluations?",
        "keywords": ["mttr", "automation", "sub-second", "milliseconds", "end-to-end", "orchestrator", "dag", "latency"],
        "model_answer": "MTTR is the average elapsed time between incident onset/detection and complete verified recovery. Human SRE triage requires 45-90 minutes. CloudSentry executes the entire cycle--anomaly detection, root cause isolation, patch synthesis, and sandbox validation--as an in-memory computational DAG, completing all phases in ~2,480 milliseconds.",
        "sample_response": "MTTR is the average elapsed time to resolve incidents. CloudSentry automates the entire end-to-end detection, RCA, and patch validation workflow in an in-memory orchestrator DAG in ~2,480 milliseconds.",
    },
]


def score_answer(user_answer: str, question_data: dict) -> dict:
    """Evaluates user response against gold-standard rubric and keyword coverage."""
    if not user_answer or not user_answer.strip():
        return {"score": 0.0, "matched_keywords": [], "feedback": "No answer provided."}

    user_text = user_answer.lower()
    keywords = question_data["keywords"]
    matched = [kw for kw in keywords if kw.lower() in user_text]

    keyword_coverage = len(matched) / max(1, len(keywords))
    length_factor = min(1.0, len(user_answer.split()) / 20.0)

    raw_score = (keyword_coverage * 70.0) + (length_factor * 30.0)
    final_score = round(min(100.0, raw_score), 1)

    if final_score >= 80:
        feedback = "Excellent! Comprehensive technical coverage and terminology."
    elif final_score >= 50:
        feedback = "Good response, but missing some key theoretical concepts or terminology."
    else:
        feedback = "Needs improvement. Review the core concepts and model answer below."

    return {
        "score": final_score,
        "matched_keywords": matched,
        "total_keywords": len(keywords),
        "feedback": feedback,
    }


def run_simulator(auto_mode: bool = False):
    """Runs the interactive or automated viva defense examination."""
    print("=" * 76)
    print(" [CLOUDSENTRY] VIVA DEFENSE & TECHNICAL INTERVIEW SIMULATOR")
    print("=" * 76)
    print(f"[*] Total Questions: {len(VIVA_QUESTIONS)}")
    print(f"[*] Mode:            {'Automated Benchmark Walkthrough' if auto_mode else 'Interactive Examination'}")
    print("-" * 76)

    total_score = 0.0

    for idx, q in enumerate(VIVA_QUESTIONS):
        print(f"\n[Q{idx+1}/10] Domain: {q['domain']}")
        print(f"Question: {q['question']}")
        print("-" * 76)

        if auto_mode:
            user_response = q["sample_response"]
            print(f"> Candidate Response:\n  \"{user_response}\"")
            time.sleep(0.2)
        else:
            try:
                user_response = input("\nType your answer (or press Enter to skip): ")
            except (EOFError, KeyboardInterrupt):
                print("\n[!] Exiting simulator.")
                break

        evaluation = score_answer(user_response, q)
        total_score += evaluation["score"]

        print(f"\n[*] Score: {evaluation['score']}/100 | {evaluation['feedback']}")
        print(f"[*] Matched Rubric Keywords: {len(evaluation['matched_keywords'])}/{evaluation['total_keywords']} ({', '.join(evaluation['matched_keywords']) if evaluation['matched_keywords'] else 'None'})")
        print("\n[+] GOLD-STANDARD MODEL ANSWER:")
        print(f"    {q['model_answer']}")
        print("=" * 76)

    average_score = round(total_score / len(VIVA_QUESTIONS), 1)
    print("\n" + "=" * 76)
    print(f" [CLOUDSENTRY] FINAL VIVA EVALUATION RESULT: {average_score} / 100")
    if average_score >= 80:
        print(" [*] Grade: OUTSTANDING (High Distinction / Industry Production Ready)")
    elif average_score >= 65:
        print(" [*] Grade: VERY GOOD (Approved with Minor Commendations)")
    else:
        print(" [*] Grade: SATISFACTORY (Review Theoretical Formulations)")
    print("=" * 76)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CloudSentry Viva Defense Simulator")
    parser.add_argument("--auto", action="store_true", help="Run automated demonstration mode")
    args = parser.parse_args()

    run_simulator(auto_mode=args.auto)
