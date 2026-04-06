# SOP: Network Loss

## Triggers
- Pods unable to communicate with each other, services, or external endpoints.
- Intermittent or complete loss of network connectivity within the cluster.
- High packet loss, latency spikes, or timeouts reported by monitoring.
- Node status shows `NetworkUnavailable` condition.
- CNI plugin errors or failed pod network setup.

## Checks (in order)
1. Verify pod network interface status: `kubectl exec <pod> -- ip addr` and `kubectl exec <pod> -- ip route` to confirm IP assignment and routing.
2. Test basic connectivity from affected pod to another pod, service, or external IP using `ping`, `curl`, or `traceroute`.
3. Check node-level networking on the affected node: run `ip addr`, `ip route`, `ip link` on the node to inspect interfaces and routes.
4. Review CNI plugin logs on the node (e.g., `/var/log/calico/cni/`, `/var/log/cilium/`, or journal logs: `journalctl -u kubelet | grep -i cni`).
5. Verify kube-proxy is running correctly: `kubectl get pods -n kube-system | grep kube-proxy` and check its logs.
6. Inspect iptables rules (if using iptables mode): `iptables-save` and verify service proxy rules are present.
7. Check for network policy denials: `kubectl describe networkpolicy` and review if policies are blocking required traffic.
8. Validate DNS resolution: `kubectl exec <pod> -- nslookup kubernetes.default.svc.cluster.local`.
9. Confirm node conditions: `kubectl describe node <node-name>` and look for `NetworkUnavailable` or `Ready` status.
10. Check for underlying infrastructure issues (e.g., switch failure, NIC malfunction) by consulting node events and hardware monitoring.

## Immediate Mitigation
- **Restart CNI pods** (e.g., Calico, Cilium, Flannel) in the `kube-system` namespace to reinitialize network policies and interfaces.
- **Restart kube-proxy** on affected nodes: `kubectl delete pod -n kube-system -l k8s-app=kube-proxy` (DaemonSet managed).
- **Delete and recreate affected pods** to obtain new IP addresses and re‑attach network interfaces.
- **Cordon and drain the node** to reschedule workloads to healthy nodes, then reboot the node if necessary.
- **Roll back recent changes** to network policies, CNI configuration, or node networking configuration.
- **Apply temporary network policy** to allow all traffic (if misconfigured policies are suspected).
- **Escalate to network infrastructure team** if node‑level or hardware issues are identified.
