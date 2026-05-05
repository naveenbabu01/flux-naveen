#!/bin/bash
# ============================================================================
# deploy.sh — Deploy MCP Server to AKS (Production)
# ============================================================================
# Prerequisites:
#   1. Azure CLI logged in: az login
#   2. AKS credentials: az aks get-credentials --resource-group rg-test --name aks-test
#   3. ACR access configured on AKS
#   4. Azure Key Vault created with secrets
# ============================================================================

set -e

# ── Variables ────────────────────────────────────────────────────────────────
RESOURCE_GROUP="rg-test"
AKS_CLUSTER="aks-test"
ACR_NAME="pythonacrtest"
IMAGE_NAME="mcp-server-prod"
IMAGE_TAG="latest"
KEY_VAULT_NAME="midodevops-test"
MANAGED_IDENTITY_NAME="mcp-server-identity"
NAMESPACE="mcp-server"

echo "═══════════════════════════════════════════════════════════════"
echo "  MCP Azure DevOps Server — Production Deployment"
echo "═══════════════════════════════════════════════════════════════"

# ── Step 1: Create Azure Key Vault and add secrets ──────────────────────────
echo ""
echo "📦 Step 1: Setting up Azure Key Vault..."
az keyvault create \
  --name $KEY_VAULT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location eastus \
  --enable-rbac-authorization true \
  2>/dev/null || echo "  Key Vault already exists"

echo "  Adding secrets to Key Vault..."
echo "  ⚠️  Run these manually with your actual values:"
echo "    az keyvault secret set --vault-name $KEY_VAULT_NAME --name github-token --value <YOUR_GITHUB_PAT>"
echo "    az keyvault secret set --vault-name $KEY_VAULT_NAME --name jira-api-token --value <YOUR_JIRA_TOKEN>"
echo "    az keyvault secret set --vault-name $KEY_VAULT_NAME --name app-insights-api-key --value <YOUR_KEY>"

# ── Step 2: Create Managed Identity ────────────────────────────────────────
echo ""
echo "🔐 Step 2: Creating Managed Identity..."
az identity create \
  --name $MANAGED_IDENTITY_NAME \
  --resource-group $RESOURCE_GROUP \
  2>/dev/null || echo "  Managed Identity already exists"

IDENTITY_CLIENT_ID=$(az identity show \
  --name $MANAGED_IDENTITY_NAME \
  --resource-group $RESOURCE_GROUP \
  --query clientId -o tsv)

IDENTITY_OBJECT_ID=$(az identity show \
  --name $MANAGED_IDENTITY_NAME \
  --resource-group $RESOURCE_GROUP \
  --query principalId -o tsv)

echo "  Managed Identity Client ID: $IDENTITY_CLIENT_ID"

# ── Step 3: Assign roles to Managed Identity ────────────────────────────────
echo ""
echo "🔑 Step 3: Assigning RBAC roles..."

SUBSCRIPTION_ID=$(az account show --query id -o tsv)

# Key Vault Secrets User (read secrets)
az role assignment create \
  --assignee $IDENTITY_OBJECT_ID \
  --role "Key Vault Secrets User" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEY_VAULT_NAME" \
  2>/dev/null || echo "  Key Vault role already assigned"

# AKS Cluster User Role (get kubeconfig)
az role assignment create \
  --assignee $IDENTITY_OBJECT_ID \
  --role "Azure Kubernetes Service Cluster User Role" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.ContainerService/managedClusters/$AKS_CLUSTER" \
  2>/dev/null || echo "  AKS role already assigned"

# Monitoring Reader
az role assignment create \
  --assignee $IDENTITY_OBJECT_ID \
  --role "Monitoring Reader" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP" \
  2>/dev/null || echo "  Monitor role already assigned"

# Cost Management Reader
az role assignment create \
  --assignee $IDENTITY_OBJECT_ID \
  --role "Cost Management Reader" \
  --scope "/subscriptions/$SUBSCRIPTION_ID" \
  2>/dev/null || echo "  Cost role already assigned"

# ── Step 4: Build and push Docker image ────────────────────────────────────
echo ""
echo "🐳 Step 4: Building and pushing Docker image..."
az acr build \
  --registry $ACR_NAME \
  --image $IMAGE_NAME:$IMAGE_TAG \
  .

# ── Step 5: Update ServiceAccount with Managed Identity ────────────────────
echo ""
echo "⚙️  Step 5: Updating Kubernetes ServiceAccount..."
sed -i "s/<YOUR-MANAGED-IDENTITY-CLIENT-ID>/$IDENTITY_CLIENT_ID/g" k8s/serviceaccount.yaml

# ── Step 6: Deploy to AKS ──────────────────────────────────────────────────
echo ""
echo "🚀 Step 6: Deploying to AKS..."
az aks get-credentials --resource-group $RESOURCE_GROUP --name $AKS_CLUSTER --overwrite-existing
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/serviceaccount.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml

# ── Step 7: Setup Workload Identity Federation ─────────────────────────────
echo ""
echo "🔗 Step 7: Setting up Workload Identity Federation..."
AKS_OIDC_ISSUER=$(az aks show \
  --resource-group $RESOURCE_GROUP \
  --name $AKS_CLUSTER \
  --query "oidcIssuerProfile.issuerUrl" -o tsv)

az identity federated-credential create \
  --name "mcp-server-federated" \
  --identity-name $MANAGED_IDENTITY_NAME \
  --resource-group $RESOURCE_GROUP \
  --issuer $AKS_OIDC_ISSUER \
  --subject "system:serviceaccount:$NAMESPACE:mcp-server-sa" \
  --audience "api://AzureADTokenExchange" \
  2>/dev/null || echo "  Federated credential already exists"

# ── Step 8: Verify ─────────────────────────────────────────────────────────
echo ""
echo "✅ Step 8: Verifying deployment..."
kubectl rollout status deployment/mcp-server -n $NAMESPACE --timeout=120s

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ MCP Server deployed successfully!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  Get external IP:"
echo "    kubectl get svc mcp-server-svc -n $NAMESPACE"
echo ""
echo "  Test health:"
echo "    curl http://<EXTERNAL-IP>/health"
echo ""
echo "  Claude Desktop config (HTTP/SSE mode):"
echo "    {"
echo "      \"mcpServers\": {"
echo "        \"azure-devops-prod\": {"
echo "          \"url\": \"http://<EXTERNAL-IP>/sse\""
echo "        }"
echo "      }"
echo "    }"
echo ""
