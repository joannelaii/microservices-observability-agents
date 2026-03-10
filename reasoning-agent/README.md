# Reasoning Agent

The purpose of this reasoning agent is to:
* Classify every telemetry signal (metrics, traces, logs) as NORMAL, WARNING, or CRITICAL
* Generate ranked root-cause hypotheses with supporting and counter evidence
* Infer causal chains between signals (e.g. memory pressure → GC pauses → latency spikes)
* Identify telemetry gaps that would be needed to confirm or rule out hypotheses

The reasoning agent follows a multi-pass analytical workflow: Telemetry input + SOP/Code agent context -> Classify signals -> Hypothesise root causes and causal chains -> Consolidate into structured diagnostic summary

LangGraph nodes:
1. `classify_signals`: parses raw telemetry and produces a per-signal NORMAL / WARNING / CRITICAL classification table
2. `hypothesise`: generates ranked root-cause hypotheses, causal chains, and telemetry gaps using classified signals and context from the SOP and Code agents
3. `summarise`: consolidates all intermediate reasoning into a single structured `reasoning_summary` passed to the main orchestrator agent