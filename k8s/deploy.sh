#!/bin/bash

# A2A SWE-bench Kubernetes Deployment Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="a2a-swe-bench"
CONTEXT="${K8S_CONTEXT:-}"

echo -e "${GREEN}A2A SWE-bench Kubernetes Deployment${NC}"
echo "======================================"

# Check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        echo -e "${RED}kubectl is not installed${NC}"
        exit 1
    fi
    
    # Check kustomize
    if ! command -v kustomize &> /dev/null; then
        echo -e "${YELLOW}kustomize is not installed, using kubectl kustomize${NC}"
        USE_KUBECTL_KUSTOMIZE=true
    fi
    
    # Check cluster connection
    if ! kubectl cluster-info &> /dev/null; then
        echo -e "${RED}Cannot connect to Kubernetes cluster${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}Prerequisites check passed${NC}"
}

# Create namespace
create_namespace() {
    echo -e "${YELLOW}Creating namespace...${NC}"
    kubectl apply -f 00-namespace.yaml
}

# Deploy secrets
deploy_secrets() {
    echo -e "${YELLOW}Deploying secrets...${NC}"
    
    # Check if secrets already exist
    if kubectl get secret database-secret -n $NAMESPACE &> /dev/null; then
        echo -e "${YELLOW}Secrets already exist, skipping...${NC}"
    else
        # Generate random passwords for production
        DB_PASSWORD=$(openssl rand -base64 32)
        REDIS_PASSWORD=$(openssl rand -base64 32)
        GRAFANA_PASSWORD=$(openssl rand -base64 16)
        
        # Create secrets
        kubectl create secret generic database-secret \
            --from-literal=POSTGRES_USER=a2a_user \
            --from-literal=POSTGRES_PASSWORD=$DB_PASSWORD \
            --from-literal=DATABASE_URL="postgresql://a2a_user:$DB_PASSWORD@postgres-service:5432/a2a_swe_bench" \
            -n $NAMESPACE
        
        kubectl create secret generic redis-secret \
            --from-literal=REDIS_PASSWORD=$REDIS_PASSWORD \
            -n $NAMESPACE
        
        kubectl create secret generic monitoring-secrets \
            --from-literal=GRAFANA_ADMIN_PASSWORD=$GRAFANA_PASSWORD \
            -n $NAMESPACE
        
        echo -e "${GREEN}Secrets created successfully${NC}"
        echo -e "${YELLOW}Grafana admin password: $GRAFANA_PASSWORD${NC}"
    fi
}

# Deploy with kustomize
deploy_with_kustomize() {
    echo -e "${YELLOW}Deploying with kustomize...${NC}"
    
    if [ "$USE_KUBECTL_KUSTOMIZE" = true ]; then
        kubectl apply -k .
    else
        kustomize build . | kubectl apply -f -
    fi
}

# Deploy individually
deploy_individually() {
    echo -e "${YELLOW}Deploying manifests individually...${NC}"
    
    kubectl apply -f 01-configmap.yaml
    kubectl apply -f 02-secrets.yaml
    kubectl apply -f 03-databases.yaml
    
    # Wait for databases to be ready
    echo -e "${YELLOW}Waiting for databases to be ready...${NC}"
    kubectl wait --for=condition=ready pod -l app=postgres -n $NAMESPACE --timeout=120s
    kubectl wait --for=condition=ready pod -l app=redis -n $NAMESPACE --timeout=120s
    
    kubectl apply -f 04-deployments.yaml
    kubectl apply -f 05-services.yaml
    kubectl apply -f 06-monitoring.yaml
    kubectl apply -f 07-ingress.yaml
    kubectl apply -f 08-autoscaling.yaml
    kubectl apply -f 09-network-policies.yaml
}

# Check deployment status
check_status() {
    echo -e "${YELLOW}Checking deployment status...${NC}"
    
    kubectl get pods -n $NAMESPACE
    kubectl get services -n $NAMESPACE
    kubectl get ingress -n $NAMESPACE
    
    # Get external IP
    EXTERNAL_IP=$(kubectl get service a2a-server-external -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
    if [ -n "$EXTERNAL_IP" ]; then
        echo -e "${GREEN}External IP: $EXTERNAL_IP${NC}"
    else
        echo -e "${YELLOW}External IP pending...${NC}"
    fi
}

# Main deployment
main() {
    check_prerequisites
    create_namespace
    deploy_secrets
    
    # Choose deployment method
    if [ -f "kustomization.yaml" ]; then
        deploy_with_kustomize
    else
        deploy_individually
    fi
    
    check_status
    
    echo -e "${GREEN}Deployment completed successfully!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Update DNS records for your domain"
    echo "2. Configure TLS certificates with cert-manager"
    echo "3. Update secret values for production"
    echo "4. Access Grafana at http://<external-ip>:3000"
    echo "5. Monitor pods: kubectl get pods -n $NAMESPACE -w"
}

# Handle different commands
case "${1:-deploy}" in
    deploy)
        main
        ;;
    delete)
        echo -e "${RED}Deleting A2A deployment...${NC}"
        kubectl delete namespace $NAMESPACE
        ;;
    status)
        check_status
        ;;
    logs)
        kubectl logs -n $NAMESPACE -l app=${2:-a2a-server} --tail=100 -f
        ;;
    *)
        echo "Usage: $0 {deploy|delete|status|logs <app>}"
        exit 1
        ;;
esac