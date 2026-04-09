# SOP: Pod Failure Detection

## Keywords
ImagePullBackOff, ErrImagePull, pod pending, pod not ready, readiness probe failure, scheduling failure, pod unhealthy, pod failed, pod unknown state, image pull error

## Triggers
- Pod in `Pending`, `ImagePullBackOff`, `ErrImagePull`, `Failed`, `Unknown` state.
- Pod not ready for extended period (readiness probe failing).
- Alert from monitoring indicating pod is down or unhealthy.

## Checks (in order)
1. Run `kubectl describe pod <pod-name>` and examine the `Events` section for immediate errors (e.g., image pull, scheduling failures).
2. Check pod status and conditions: `kubectl get pod <pod-name> -o wide` and `kubectl get pod <pod-name> -o jsonpath='{.status.conditions}'`.
3. For image‑related failures (`ImagePullBackOff`, `ErrImagePull`): verify image name and tag, check image pull secrets, and test connectivity to the container registry.
4. For `Pending` state: inspect node resources (CPU, memory), node selector/affinity, persistent volume claims (PVC) status, and taints/tolerations on the node.
5. If pod is `CrashLoopBackOff`, follow the “Pod CrashLoopBackOff” SOP for log analysis and startup command verification.
6. Verify pod network connectivity: check service endpoints, confirm CNI plugins are functioning, and test pod‑to‑pod communication if necessary.
7. Review container logs for any running containers (`kubectl logs <pod-name>`) or previous logs (`kubectl logs <pod-name> --previous`).
8. Validate resource limits and requests against available node capacity, and check for any resource quota violations at the namespace level.

## Immediate Mitigation
- **Image pull failure**: correct the image name/tag, fix image pull secrets, or ensure the registry is accessible.
- **Pending due to insufficient resources**: scale down other workloads, add nodes, or reduce resource requests/limits.
- **Configuration errors**: correct the ConfigMap, Secret, or pod spec; restart the pod if needed.
- **Node issues**: cordon/drain the problematic node and reschedule the pod.
- **Roll back**: revert recent deployment changes if a misconfiguration was introduced.
- **Restart**: delete the pod (if managed by a controller) to let it be recreated with a fresh state.
