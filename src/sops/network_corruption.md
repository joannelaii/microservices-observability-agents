# SOP: Network Corruption

## Keywords
packet corruption, DNS failure, connection reset, intermittent network, CNI error, network policy denial, checksum error, intermittent timeout, DNS resolution failure, service endpoint unreachable

## Triggers
- Pods unable to communicate with each other or with services.
- Intermittent connection resets, timeouts, or high latency.
- DNS resolution failures within the cluster.
- Service endpoints unreachable despite pods running.
- Network policy denials causing unexpected blocks.
- CNI plugin errors in node logs.

## Checks (in order)
1. Verify pod network connectivity: run `kubectl exec <pod> -- ping <target-ip>` or `curl` to test basic connectivity between pods.
2. Check DNS resolution: `kubectl exec <pod> -- nslookup kubernetes.default.svc.cluster.local` or use `dig`.
3. Inspect service endpoints: `kubectl get endpoints <service-name>` and confirm they match healthy pod IPs.
4. Review network policies: `kubectl get networkpolicy -A` and examine if policies are blocking traffic; check policy rules and labels.
5. Examine CNI logs on affected nodes (e.g., /var/log/messages or CNI plugin logs like Calico, Cilium, Flannel).
6. Check node network interfaces: `ip addr`, `ip route`, and verify no duplicate IPs, misconfigured routes, or interface flapping.
7. Validate kube-proxy mode (iptables/IPVS) and check iptables rules for service connectivity: `iptables-save | grep <service-name>`.
8. Inspect pod IPAM allocation: ensure IPs are correctly assigned and no conflicts; check CNI IP pool status.
9. Test with a temporary debug pod (e.g., `busybox` or `netshoot`) to isolate namespace‑level or node‑level issues.
10. Review cluster networking logs (kube-proxy, CNI controller) for errors.

## Immediate Mitigation
- **Restart kube-proxy** on affected nodes: `kubectl delete pod -n kube-system -l k8s-app=kube-proxy` (if DaemonSet‑managed).
- **Restart CNI pods** (e.g., Calico, Cilium) to reapply network configurations.
- **Delete and recreate problematic pods** to obtain new IP addresses and reconnect.
- **Recreate service endpoints** by scaling the associated deployment/controller down and up.
- **Temporarily relax network policies** to allow traffic while investigating.
- **Reboot the node** if network stack appears corrupted (as last resort).
- **Restart coreDNS**: `kubectl rollout restart deployment -n kube-system coredns`.
- **Roll back recent changes** to network policies, CNI configuration, or node updates.
