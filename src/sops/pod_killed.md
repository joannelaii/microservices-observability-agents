# SOP: Pod Killed (OOMKilled, Evicted, Terminated)

## Keywords
OOMKilled, evicted, exit code 137, SIGKILL, memory limit exceeded, pod terminated, disk pressure, preempted, pod killed, node pressure eviction

## Triggers
- Pod status shows `OOMKilled`, `Evicted`, or `Terminated`.
- Container exits with exit code 137 (SIGKILL) or 143 (SIGTERM).
- Pod disappears or restarts without explicit user action.

## Checks (in order)
1. Inspect pod events: `kubectl describe pod <pod-name>` and look for `Killing`, `Evicted`, or `OOMKilling` events.
2. Check container exit codes and reason: `kubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[*].lastState.terminated}'`.
3. For `OOMKilled`: review memory usage before termination. Check `kubectl top pod <pod-name>` (if metrics available) and examine memory limits vs actual usage.
4. For `Evicted`: check node pressure conditions (memory, disk, PID) via `kubectl describe node <node-name>` and review node events.
5. Verify if pod exceeded its ephemeral storage limit (`ephemeral-storage` request/limit).
6. Examine container logs for high memory/disk usage patterns leading up to termination: `kubectl logs <pod-name> --previous`.
7. Check if pod was terminated due to preemption (higher priority pod scheduled) by reviewing node events or scheduler logs.
8. Confirm if liveness/readiness probe failures led to container restart counts exceeding thresholds.
9. Validate resource limits and requests against actual workload requirements; compare with node capacity.

## Immediate Mitigation
- **OOMKilled**: increase memory limits in the pod spec; optimize application memory usage; set appropriate memory requests to guarantee scheduling.
- **Evicted due to disk pressure**: clean up unused images/containers on node; increase ephemeral‑storage limits; add node capacity.
- **Evicted due to memory pressure**: reduce memory usage of pods; increase memory limits; add nodes or resize node pool.
- **Preempted**: review priority class configuration; adjust pod priorities or scale up node pool to avoid preemption.
- **Probe failures**: fix application health endpoints; adjust probe thresholds (initialDelaySeconds, failureThreshold, periodSeconds).
- **Roll back**: revert recent changes to resource limits or application code if the issue started after an update.
