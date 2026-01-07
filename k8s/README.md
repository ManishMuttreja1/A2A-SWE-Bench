# A2A SWE-bench Kubernetes Deployment

Production-ready Kubernetes manifests for deploying the A2A SWE-bench evaluation system.

## Architecture

The deployment includes:

- **Core Services**
  - A2A Server (3 replicas, auto-scaling)
  - Synthesis Engine (2 replicas, auto-scaling)
  - Green Agent Service (2 replicas, auto-scaling)
  - Trajectory Analyzer (1 replica with VPA)

- **Data Layer**
  - PostgreSQL (StatefulSet with persistent storage)
  - Redis (StatefulSet with persistent storage)

- **Monitoring Stack**
  - Prometheus (metrics collection)
  - Grafana (visualization)
  - Alertmanager (alert routing)

- **Networking**
  - NGINX Ingress Controller
  - Network Policies for security
  - TLS termination

## Prerequisites

- Kubernetes cluster (1.24+)
- kubectl configured
- Ingress controller installed
- Storage class available for PVCs
- Optional: cert-manager for TLS certificates

## Quick Start

```bash
# Deploy everything
chmod +x deploy.sh
./deploy.sh deploy

# Check status
./deploy.sh status

# View logs
./deploy.sh logs a2a-server

# Delete deployment
./deploy.sh delete
```

## Manual Deployment

### 1. Create Namespace

```bash
kubectl apply -f 00-namespace.yaml
```

### 2. Configure Secrets

Edit `02-secrets.yaml` and replace placeholder values:

```bash
# Generate secure passwords
openssl rand -base64 32  # For database
openssl rand -base64 32  # For Redis
openssl rand -base64 16  # For Grafana

# Create secrets
kubectl apply -f 02-secrets.yaml
```

### 3. Deploy Components

```bash
# Deploy in order
kubectl apply -f 01-configmap.yaml
kubectl apply -f 03-databases.yaml

# Wait for databases
kubectl wait --for=condition=ready pod -l app=postgres -n a2a-swe-bench --timeout=120s
kubectl wait --for=condition=ready pod -l app=redis -n a2a-swe-bench --timeout=120s

# Deploy applications
kubectl apply -f 04-deployments.yaml
kubectl apply -f 05-services.yaml
kubectl apply -f 06-monitoring.yaml
kubectl apply -f 07-ingress.yaml
kubectl apply -f 08-autoscaling.yaml
kubectl apply -f 09-network-policies.yaml
```

### 4. Using Kustomize

```bash
# Deploy with kustomize
kubectl apply -k .

# Or build and apply
kustomize build . | kubectl apply -f -
```

## Configuration

### Environment Variables

Key configuration in `01-configmap.yaml`:

- `A2A_SERVER_PORT`: API server port (default: 8080)
- `MAX_CONCURRENT_TASKS`: Maximum concurrent evaluations
- `SYNTHESIS_TTL_HOURS`: Cache TTL for synthesis engine
- `MONITORING_PORT`: Metrics endpoint port

### Scaling

Horizontal Pod Autoscaling is configured for:

- **A2A Server**: 3-10 replicas (CPU: 70%, Memory: 80%)
- **Synthesis Engine**: 2-8 replicas (CPU: 75%, Memory: 85%)
- **Green Agent**: 2-6 replicas (CPU: 70%, Tasks: 10/pod)

Adjust in `08-autoscaling.yaml`.

### Resource Limits

Default resource allocations:

| Service | Request CPU | Request Memory | Limit CPU | Limit Memory |
|---------|------------|----------------|-----------|--------------|
| A2A Server | 500m | 1Gi | 2 | 2Gi |
| Synthesis Engine | 1 | 2Gi | 4 | 4Gi |
| Green Agent | 500m | 1Gi | 2 | 2Gi |
| PostgreSQL | 500m | 1Gi | 1 | 2Gi |
| Redis | 250m | 512Mi | 500m | 2Gi |

## Monitoring

### Access Dashboards

```bash
# Port-forward Grafana
kubectl port-forward -n a2a-swe-bench svc/grafana-service 3000:3000

# Port-forward Prometheus
kubectl port-forward -n a2a-swe-bench svc/prometheus-service 9090:9090

# Default Grafana credentials
# Username: admin
# Password: <from monitoring-secrets>
```

### Metrics Endpoints

All services expose metrics on port 9090:
- `/metrics` - Prometheus format metrics
- `/health` - Health status
- `/ready` - Readiness probe

### Alerts

Configured alerts include:
- High CPU/Memory usage
- Database connection failures
- High error rates
- Synthesis failures
- Agent disconnections

Configure alert channels in `alertmanager-config`.

## Security

### Network Policies

- Default deny all ingress
- Explicit allow rules for service communication
- Database access restricted to authorized pods
- External egress for API calls

### Secrets Management

For production:
1. Use Sealed Secrets or External Secrets Operator
2. Enable encryption at rest
3. Rotate credentials regularly
4. Use separate credentials per environment

### TLS Configuration

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Create ClusterIssuer for Let's Encrypt
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@a2a-swe-bench.io
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -n a2a-swe-bench
kubectl describe pod <pod-name> -n a2a-swe-bench
kubectl logs <pod-name> -n a2a-swe-bench
```

### Database Connection Issues

```bash
# Test PostgreSQL connection
kubectl exec -it postgres-0 -n a2a-swe-bench -- psql -U a2a_user -d a2a_swe_bench

# Test Redis connection
kubectl exec -it redis-0 -n a2a-swe-bench -- redis-cli ping
```

### Ingress Not Working

```bash
# Check ingress controller
kubectl get pods -n ingress-nginx
kubectl get ingress -n a2a-swe-bench
kubectl describe ingress a2a-ingress -n a2a-swe-bench
```

### Performance Issues

```bash
# Check HPA status
kubectl get hpa -n a2a-swe-bench

# Check resource usage
kubectl top pods -n a2a-swe-bench
kubectl top nodes
```

## Production Checklist

- [ ] Replace all placeholder secrets
- [ ] Configure proper domain names in Ingress
- [ ] Set up TLS certificates
- [ ] Configure backup for databases
- [ ] Set up monitoring alerts
- [ ] Configure log aggregation
- [ ] Implement RBAC policies
- [ ] Set up CI/CD pipeline
- [ ] Configure disaster recovery
- [ ] Load test the deployment

## Backup and Recovery

### Database Backup

```bash
# Backup PostgreSQL
kubectl exec -n a2a-swe-bench postgres-0 -- pg_dump -U a2a_user a2a_swe_bench > backup.sql

# Backup Redis
kubectl exec -n a2a-swe-bench redis-0 -- redis-cli --rdb /tmp/backup.rdb
kubectl cp a2a-swe-bench/redis-0:/tmp/backup.rdb ./redis-backup.rdb
```

### Restore

```bash
# Restore PostgreSQL
kubectl exec -i -n a2a-swe-bench postgres-0 -- psql -U a2a_user a2a_swe_bench < backup.sql

# Restore Redis
kubectl cp ./redis-backup.rdb a2a-swe-bench/redis-0:/tmp/backup.rdb
kubectl exec -n a2a-swe-bench redis-0 -- redis-cli shutdown nosave
kubectl exec -n a2a-swe-bench redis-0 -- cp /tmp/backup.rdb /data/dump.rdb
```

## Support

For issues and questions:
- GitHub Issues: https://github.com/a2a-swe-bench/k8s
- Documentation: https://docs.a2a-swe-bench.io
- Slack: #a2a-swe-bench