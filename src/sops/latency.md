# SOP: High Latency / Slow Request Processing

## Keywords
request latency, p95, p99, slow requests, high response time, HTTP timeout, response time degradation, latency spike, slow RPC, slow endpoint

## Triggers
- p95/p99 latency exceeds the alert threshold for a sustained period.
- Requests, RPCs, or message processing complete successfully but are much slower than normal.
- Consumer or worker processing time increases while traffic is still present.
- User-facing operations time out or feel slow without a corresponding spike in error rate.

## Checks (in order)
1. Confirm the signal: verify latency is elevated while request or processing volume is still present.
2. Determine scope: identify the affected service, endpoint, RPC method, job, or consumer operation.
3. Compare latency with error rate and throughput to determine whether this is pure slowness or slowness with failures.
4. Check recent traces for the affected flow and identify the slowest span(s) or repeated slow spans.
5. Determine whether latency is internal or downstream:
   - Internal processing: long `INTERNAL` spans, CPU-heavy work, serialization, batching, retries, queue handling.
   - Downstream dependency: long `CLIENT` spans, slow database/API/RPC calls, DNS/connectivity delays.
6. Inspect service resource health during the incident window:
   - CPU saturation or throttling
   - memory pressure / GC pauses
   - thread pool, worker, or connection pool saturation
7. Check queue- or consumer-specific indicators if applicable:
   - queue depth
   - consumer lag
   - partition imbalance
   - batch size growth
8. Review recent deployment, config, feature-flag, dependency, or traffic-pattern changes around the incident window.
9. Check pod restarts, readiness issues, or node pressure that may be degrading performance without causing full failure.
10. Compare with baseline latency before the incident to see whether the slowdown is sudden or gradual.

## Immediate Mitigation
- **Downstream dependency slow**: reduce dependency pressure, fail over if possible, increase timeout budgets only if safe, and investigate the dependency directly.
- **CPU saturation / throttling**: increase CPU requests/limits if appropriate, scale out replicas, and reduce expensive work in the hot path.
- **Memory / GC pressure**: increase memory if safe, reduce allocation-heavy work, and investigate leaks or oversized batches.
- **Queue / consumer lag**: increase consumer concurrency, rebalance partitions, reduce batch size, or scale consumers horizontally.
- **Connection pool / worker exhaustion**: raise pool limits carefully, reduce blocking calls, and inspect stuck or long-running tasks.
- **Recent bad rollout or config change**: roll back the change or disable the feature flag if the timing matches the regression.
- **Traffic spike**: scale out the affected service and confirm autoscaling is functioning correctly.

## Evidence to Capture
- Affected service and operation name
- Latency values (for example p95/p99 and duration of impact)
- Request/processing rate during the incident
- Error rate during the same period
- Slowest spans and their durations
- Resource usage during the window
- Queue lag / backlog if applicable
- Recent changes near incident start time

## Escalation Criteria
- Latency remains above threshold after mitigation.
- User-facing impact is severe or spreads across multiple services.
- Slowdown source cannot be isolated from traces, metrics, and logs.
- The issue appears tied to an external dependency or platform-level bottleneck.
