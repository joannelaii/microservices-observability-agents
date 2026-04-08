# Kafka Issues

## Symptoms
- High latency in message processing
- Connection failures to brokers
- Consumer lag increasing
- Producer timeouts
- Broker unavailability

## Common Causes
- Broker nodes down or restarting
- Network partitions between brokers
- Insufficient broker resources (CPU, memory)
- Disk space full on brokers
- Configuration issues (e.g., replication factor, partitions)
- ZooKeeper issues affecting broker coordination

## Diagnostic Steps
1. Check broker health and status
2. Verify network connectivity between producers/consumers and brokers
3. Monitor consumer lag and producer metrics
4. Check disk usage and I/O on broker nodes
5. Review broker logs for errors
6. Validate topic and partition configurations

## Mitigation
- Restart failed brokers
- Scale up broker resources
- Rebalance partitions
- Fix network issues
- Clean up disk space
- Update configurations