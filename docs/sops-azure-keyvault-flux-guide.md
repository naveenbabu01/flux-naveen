# SOPS + Azure Key Vault + Flux CD — Complete Guide

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DEVELOPER WORKFLOW                          │
│                                                                     │
│  1. Create plain Secret YAML                                       │
│  2. Encrypt with SOPS CLI (uses Azure Key Vault key)               │
│  3. Commit & Push encrypted secret to Git                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     GITHUB REPOSITORY                               │
│                                                                     │
│  flux-clusters/dev-cluster/                                        │
│  ├── .sops.yaml                    ← SOPS config (which key to use)│
│  ├── sops-demo-secret.yaml         ← Encrypted secret (safe in Git)│
│  ├── sops-demo-kustomization.yaml  ← Flux Kustomization            │
│  └── flux-system/                                                  │
│      ├── gotk-components.yaml      ← Flux controllers              │
│      ├── gotk-sync.yaml            ← Flux GitRepository + Kustom.  │
│      └── kustomization.yaml                                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                      Flux pulls every 1m
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    KUBERNETES CLUSTER                                │
│                                                                     │
│  flux-system namespace                                             │
│  ┌───────────────────────────────────────────────────────────┐     │
│  │  source-controller        → Fetches Git repo              │     │
│  │  kustomize-controller     → Applies manifests + DECRYPTS  │     │
│  │  helm-controller          → Manages Helm releases         │     │
│  │  notification-controller  → Sends alerts                  │     │
│  │  image-reflector-ctrl     → Scans image registries        │     │
│  │  image-automation-ctrl    → Updates image tags            │     │
│  └──────────────────────┬────────────────────────────────────┘     │
│                         │                                           │
│          kustomize-controller sees                                  │
│          decryption.provider: sops                                  │
│                         │                                           │
│                         ▼                                           │
│              Calls Azure Key Vault                                  │
│              to DECRYPT the secret                                  │
│                         │                                           │
│                         ▼                                           │
│  ┌──────────────────────────────────────┐                          │
│  │  Secret: sops-demo-secret            │                          │
│  │  (Decrypted & applied to cluster)    │                          │
│  │  DB_USERNAME: admin                  │                          │
│  │  DB_PASSWORD: SuperSecret123!        │                          │
│  │  API_KEY: my-secret-api-key          │                          │
│  └──────────────────────────────────────┘                          │
└─────────────────────────────────────────────────────────────────────┘
                               ▲
                               │
                    Decrypt API call
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    AZURE KEY VAULT                                   │
│                                                                     │
│  Vault: midodevops-test                                            │
│  Key:   sops-terraform                                             │
│  URL:   https://midodevops-test.vault.azure.net/keys/sops-terraform│
│                                                                     │
│  Access Policies:                                                  │
│  ├── Developer user     → encrypt, decrypt, get, list              │
│  └── kustomize-controller → encrypt, decrypt, get, list            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Flow Summary

```
Developer                 GitHub                  Flux (K8s)              Azure Key Vault
   │                        │                        │                        │
   │ 1. Create secret YAML  │                        │                        │
   │──────────────────────► │                        │                        │
   │                        │                        │                        │
   │ 2. sops --encrypt ─────┼────────────────────────┼───── encrypt call ────►│
   │    (encrypts values)   │                        │                        │
   │◄───────────────────────┼────────────────────────┼──── encrypted key ─────│
   │                        │                        │                        │
   │ 3. git commit & push   │                        │                        │
   │──────────────────────► │                        │                        │
   │                        │                        │                        │
   │                        │ 4. Flux pulls repo     │                        │
   │                        │──────────────────────► │                        │
   │                        │                        │                        │
   │                        │                        │ 5. Decrypt call ──────►│
   │                        │                        │◄── decrypted key ──────│
   │                        │                        │                        │
   │                        │                        │ 6. Apply plain Secret  │
   │                        │                        │    to cluster          │
   │                        │                        │                        │
```

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Flux CLI | v2.x | Bootstrap and manage Flux |
| SOPS | v3.9.4+ | Encrypt/decrypt secrets locally |
| Azure CLI | v2.x | Manage Azure resources |
| kubectl | v1.x | Interact with Kubernetes |

---

## Step-by-Step Implementation

### Step 1: Install SOPS

SOPS (Secrets OPerationS) is a CLI tool to encrypt/decrypt files.

```powershell
# Download SOPS for Windows
Invoke-WebRequest -Uri "https://github.com/getsops/sops/releases/download/v3.9.4/sops-v3.9.4.exe" `
  -OutFile "$env:USERPROFILE\sops.exe" -UseBasicParsing

# Verify installation
& "$env:USERPROFILE\sops.exe" --version
# Output: sops 3.9.4
```

---

### Step 2: Azure Key Vault Setup

We used an existing Azure Key Vault with a key already created.

**Key Vault Details:**
- **Vault Name:** `midodevops-test`
- **Vault URL:** `https://midodevops-test.vault.azure.net/`
- **Key Name:** `sops-terraform`
- **Key Identifier:** `https://midodevops-test.vault.azure.net/keys/sops-terraform/cd171914eac24937b3877c6196457ce2`

**If you need to create a new Key Vault and key:**
```bash
# Create resource group
az group create --name rg-flux-sops --location eastus

# Create Key Vault
az keyvault create --name my-flux-sops-kv --resource-group rg-flux-sops --location eastus

# Create a key for SOPS
az keyvault key create --vault-name my-flux-sops-kv --name sops-key --protection software
```

---

### Step 3: Grant Key Vault Permissions

Two identities need access to the Key Vault:

#### A. Developer User (for encrypting locally)
```bash
az keyvault set-policy \
  --name midodevops-test \
  --upn "naveen@HCIGroup2.onmicrosoft.com" \
  --key-permissions encrypt decrypt get list
```

#### B. Flux kustomize-controller (for decrypting in cluster)
The kustomize-controller uses a Service Principal or Managed Identity. Get its Object ID from the error message or:
```bash
az keyvault set-policy \
  --name midodevops-test \
  --object-id "5a02b1d7-ec10-43b9-87d3-f16d34a15126" \
  --key-permissions encrypt decrypt get list
```

> **Note:** The Object ID (`5a02b1d7-...`) comes from the Flux kustomize-controller's identity (Service Principal / Managed Identity / Workload Identity) running in the AKS cluster.

---

### Step 4: Create `.sops.yaml` Configuration File

This file tells SOPS which encryption key to use for which files.

**File:** `flux-clusters/dev-cluster/.sops.yaml`
```yaml
creation_rules:
  - path_regex: .*-secret\.yaml$
    azure_keyvault: https://midodevops-test.vault.azure.net/keys/sops-terraform/cd171914eac24937b3877c6196457ce2
```

**Explanation:**
- `path_regex: .*-secret\.yaml$` → Any file ending with `-secret.yaml` will use this rule
- `azure_keyvault` → The Azure Key Vault key URL to encrypt/decrypt

---

### Step 5: Create a Plain Text Secret

**File:** `flux-clusters/dev-cluster/sops-demo-secret.yaml`
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: sops-demo-secret
  namespace: flux-system
type: Opaque
stringData:
  DB_USERNAME: admin
  DB_PASSWORD: SuperSecret123!
  API_KEY: my-secret-api-key
```

> ⚠️ **This is the UNENCRYPTED version. Do NOT commit this to Git!**

---

### Step 6: Encrypt the Secret with SOPS

```powershell
# Navigate to the directory containing .sops.yaml
cd C:\Git_Reops\flux-naveen-1\flux-clusters\dev-cluster

# Encrypt the file in-place (only encrypts stringData)
& "$env:USERPROFILE\sops.exe" --encrypt --in-place --encrypted-regex "^(data|stringData)$" sops-demo-secret.yaml
```

**What `--encrypted-regex "^(data|stringData)$"` does:**
- Only encrypts the `data` and `stringData` fields
- Leaves `apiVersion`, `kind`, `metadata` readable
- This way you can still see WHAT the secret is, but not the VALUES

**After encryption, the file looks like:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: sops-demo-secret
  namespace: flux-system
type: Opaque
stringData:
  DB_USERNAME: ENC[AES256_GCM,data:xyz123...,type:str]
  DB_PASSWORD: ENC[AES256_GCM,data:abc456...,type:str]
  API_KEY: ENC[AES256_GCM,data:def789...,type:str]
sops:
  azure_kv:
    - vaultUrl: https://midodevops-test.vault.azure.net
      key: sops-terraform
      version: cd171914eac24937b3877c6196457ce2
```

> ✅ **This encrypted version is SAFE to commit to Git!**

---

### Step 7: Create Flux Kustomization with Decryption

**File:** `flux-clusters/dev-cluster/sops-demo-kustomization.yaml`
```yaml
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: sops-demo
  namespace: flux-system
spec:
  interval: 1m0s
  path: ./flux-clusters/dev-cluster
  prune: true
  sourceRef:
    kind: GitRepository
    name: flux-system
  decryption:
    provider: sops
```

**Key field:** `decryption.provider: sops` tells Flux to decrypt any SOPS-encrypted files before applying them.

---

### Step 8: Commit and Push

```bash
git add .sops.yaml sops-demo-secret.yaml sops-demo-kustomization.yaml
git commit -m "Add SOPS encrypted secret with Azure Key Vault"
git push
```

---

### Step 9: Verify

```bash
# Force Flux to reconcile
flux reconcile kustomization sops-demo

# Check kustomization status
flux get kustomization sops-demo
# Output: READY True ✅

# Check if secret was created
kubectl get secret sops-demo-secret -n flux-system
# Output: sops-demo-secret   Opaque   3

# Verify decrypted values
kubectl get secret sops-demo-secret -n flux-system -o jsonpath="{.data.DB_USERNAME}" | base64 -d
# Output: admin ✅
```

---

## How to Edit an Encrypted Secret

```powershell
# Decrypt in-place to edit
& "$env:USERPROFILE\sops.exe" --decrypt --in-place sops-demo-secret.yaml

# Edit the file (change values)

# Re-encrypt
& "$env:USERPROFILE\sops.exe" --encrypt --in-place --encrypted-regex "^(data|stringData)$" sops-demo-secret.yaml

# Or use sops editor mode (opens in $EDITOR)
& "$env:USERPROFILE\sops.exe" sops-demo-secret.yaml

# Commit and push
git add sops-demo-secret.yaml
git commit -m "Update encrypted secret"
git push
```

---

## How Flux Communicates with Azure Key Vault

Flux's **kustomize-controller** pod runs inside the AKS cluster. When it sees `decryption.provider: sops`, it calls Azure Key Vault's decrypt API. Authentication happens automatically via the **Azure Identity chain**:

### Authentication Order

```
kustomize-controller tries to authenticate (in order):

1. Workload Identity (recommended for AKS)
   └── Pod gets a federated token via projected service account
       └── Exchanges it for an Azure AD token

2. Managed Identity (used in this setup)
   └── AKS cluster has a Managed Identity assigned
       └── kustomize-controller inherits it via IMDS
           (Instance Metadata Service at 169.254.169.254)

3. Environment Variables
   └── AZURE_TENANT_ID + AZURE_CLIENT_ID + AZURE_CLIENT_SECRET
       └── Set as env vars on the kustomize-controller pod
```

### Detailed Communication Flow

```
┌─────────────────────────┐
│  kustomize-controller   │
│  (pod in flux-system)   │
└───────────┬─────────────┘
            │
            │ 1. Calls Azure IMDS endpoint
            │    (169.254.169.254)
            │    "Give me an access token"
            ▼
┌─────────────────────────┐
│  Azure IMDS / Managed   │
│  Identity Service       │
│  (on AKS node)          │
└───────────┬─────────────┘
            │
            │ 2. Returns Azure AD token
            │    for object-id: 5a02b1d7-...
            ▼
┌─────────────────────────┐
│  kustomize-controller   │
│  now has a Bearer token │
└───────────┬─────────────┘
            │
            │ 3. POST https://midodevops-test.vault.azure.net
            │    /keys/sops-terraform/.../decrypt
            │    Authorization: Bearer <token>
            ▼
┌─────────────────────────┐
│  Azure Key Vault        │
│  Checks access policy:  │
│  Does 5a02b1d7-... have │
│  "decrypt" permission?  │
│  YES ✅ → Returns        │
│  decrypted data key     │
└─────────────────────────┘
```

### Why `az keyvault set-policy` Was Needed

The kustomize-controller's identity (`5a02b1d7-...`) initially had **no permissions** on Key Vault → `403 Forbidden`. After granting `encrypt, decrypt, get, list`, it could decrypt successfully.

### Component Roles

| Component | Role |
|---|---|
| **AKS Managed Identity** | Provides authentication token to pods |
| **IMDS (169.254.169.254)** | Token endpoint running on every AKS node |
| **Key Vault Access Policy** | Controls who can encrypt/decrypt |
| **kustomize-controller** | Uses the token to call Key Vault decrypt API |
| **SOPS metadata in secret** | Tells which Key Vault key was used for encryption |

> **Key point:** No secrets or credentials are stored in the cluster — authentication happens automatically through Azure's identity infrastructure.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `403 Forbidden - does not have keys encrypt permission` | User lacks encrypt permission on Key Vault | `az keyvault set-policy --name <vault> --upn <user> --key-permissions encrypt decrypt get list` |
| `403 Forbidden - does not have keys decrypt permission` | kustomize-controller lacks decrypt permission | `az keyvault set-policy --name <vault> --object-id <controller-oid> --key-permissions encrypt decrypt get list` |
| `cannot get sops data key` | Flux can't reach Key Vault or no permissions | Check network policies and Key Vault access policies |
| `missing Resource metadata` | Non-K8s YAML files in kustomization path | Move values files out or use a kustomization.yaml to list resources explicitly |

---

## Security Best Practices

1. **Never commit unencrypted secrets** to Git
2. **Use `--encrypted-regex`** to only encrypt sensitive fields
3. **Rotate keys** periodically in Azure Key Vault
4. **Use Workload Identity** instead of Service Principal for production
5. **Restrict Key Vault network access** using private endpoints
6. **Use separate keys** for different environments (dev/staging/prod)
7. **Add `.sops.yaml`** at the repo root for consistent encryption rules

---

## Deep Dive: How Everything Communicates

### What Each File Does

| File | Used By | Purpose |
|---|---|---|
| `.sops.yaml` | **Developer only** (sops CLI) | Convenience config so you don't type Key Vault URL every time |
| `sops-demo-secret.yaml` | **Flux** (kustomize-controller) | Contains encrypted values + `sops:` metadata with Key Vault URL |
| `sops-demo-kustomization.yaml` | **Flux** (kustomize-controller) | Tells Flux WHERE to look and to use SOPS decryption |

> **Important:** `.sops.yaml` is NOT used by Flux. Flux reads the `sops:` metadata embedded inside the encrypted file itself.

### How Kustomization and Secret File Work Together

```
sops-demo-kustomization.yaml              sops-demo-secret.yaml
  │                                          │
  │ spec:                                    │ sops:
  │   path: ./flux-clusters/dev-cluster      │   azure_kv:
  │   decryption:                            │     - vaultUrl: midodevops-test...
  │     provider: sops                       │       key: sops-terraform
  │                                          │
  │ "Scan this folder,                       │ "I'm encrypted, call this
  │  decrypt with SOPS"                      │  Key Vault to decrypt me"
  │                                          │
  └──────────────┬───────────────────────────┘
                 │
                 ▼
     kustomize-controller reads BOTH:
     1. Kustomization → knows to use SOPS
     2. Secret file → knows which Key Vault to call
```

### How Flux Identifies Azure Key Vault

Flux knows to use Azure Key Vault because of **two things**:

1. **Kustomization** has `decryption.provider: sops` → enables SOPS decryption
2. **Encrypted file** has `sops.azure_kv` metadata → tells exactly which Key Vault and key

```
kustomize-controller
  │
  │ 1. Reads Kustomization: decryption.provider = "sops"
  │    → "I need to check for SOPS encrypted files"
  │
  │ 2. Reads sops-demo-secret.yaml, sees "sops:" block
  │    → "This file IS encrypted"
  │
  │ 3. Reads sops.azure_kv.vaultUrl
  │    → "I need to call THIS Azure Key Vault"
  │
  │ 4. Authenticates via Managed Identity (IMDS 169.254.169.254)
  │    → Gets Azure AD Bearer token
  │
  │ 5. POST https://midodevops-test.vault.azure.net/.../decrypt
  │    → Sends encrypted data key, gets decrypted data key
  │
  │ 6. Uses data key to decrypt ENC[...] → plain values
  │
  │ 7. Sends plain Secret to API Server
  ▼
```

### Kustomize-Controller Passes Decrypted Values to API Server (NOT etcd)

```
kustomize-controller
       │
       │  kubectl apply (decrypted Secret)
       ▼
  API Server          ← controller talks to THIS only
       │
       │  validates & stores
       ▼
  etcd                ← only API Server talks to etcd directly

  ✅  Controller → API Server → etcd
  ❌  Controller → etcd  (NEVER happens)
```

### How the Deployment Gets Secret Values

The app **PULLS** the secret from Kubernetes — Flux does NOT push it to the app.

```
When pod starts:

Deployment YAML:
  env:
    - name: DB_PASSWORD
      valueFrom:
        secretKeyRef:
          name: sops-demo-secret    ← "I need this secret"
          key: DB_PASSWORD           ← "this specific key"

Kubelet (node agent)              API Server               etcd
       │                               │                      │
       │ "Pod needs secret             │                      │
       │  sops-demo-secret"            │                      │
       │──────────────────────────────►│                      │
       │                               │  reads secret        │
       │                               │─────────────────────►│
       │                               │◄─────────────────────│
       │   plain value returned        │                      │
       │◄──────────────────────────────│                      │
       │                                                      │
       │  Injects into container:                             │
       │  DB_PASSWORD=SuperSecret123!                         │
       ▼
  ┌─────────────────────────┐
  │ Container               │
  │ App reads env var:      │
  │ os.getenv("DB_PASSWORD")│
  │ → "SuperSecret123!"     │
  └─────────────────────────┘
```

> The Deployment doesn't know or care that the secret was encrypted in Git. It reads a normal K8s Secret.

### Alternative: Volume Mount (instead of env vars)

```yaml
# Deployment with volume mount
spec:
  volumes:
    - name: db-creds
      secret:
        secretName: sops-demo-secret
  containers:
    - volumeMounts:
        - name: db-creds
          mountPath: /etc/secrets

# App reads files:
# /etc/secrets/DB_USERNAME  → "admin"
# /etc/secrets/DB_PASSWORD  → "SuperSecret123!"
```

### One Controller, Many Kustomizations

Creating multiple Kustomization resources does NOT create multiple controllers:

```
flux-system namespace
  CONTROLLERS (1 pod each, always running):
  ┌───────────────────────────────────────┐
  │  kustomize-controller  (1 pod only)   │ ← SINGLE controller
  └──────────────────┬────────────────────┘
                     │ watches ALL Kustomizations:
                     ├── flux-system
                     ├── sops-demo
                     ├── 2-demo-kustomize-git-bb-app
                     └── 3-demo-kustomize-git-bb-app
```

### Complete End-to-End Timeline

```
TIME     WHO                      DOES WHAT
─────    ───                      ─────────
t=0      Developer                Creates plain secret YAML
t=0      SOPS CLI                 Encrypts via Azure Key Vault → ENC[...] values
t=0      Developer                git commit & push (encrypted file)
         ─── DEVELOPER DONE ───

t=1m     Flux source-controller   Pulls Git repo (every interval)
t=1m     Flux kustomize-ctrl      Reads Kustomization → decryption: sops
t=1m     Flux kustomize-ctrl      Reads encrypted file → sees sops.azure_kv
t=1m     Flux kustomize-ctrl      Authenticates to Azure via Managed Identity
t=1m     Flux kustomize-ctrl      Calls Key Vault → decrypts data key
t=1m     Flux kustomize-ctrl      Decrypts ENC[...] → plain values
t=1m     Flux kustomize-ctrl      Sends plain Secret to API Server → stored in etcd
         ─── FLUX DONE ───

t=2m     Kubelet                  Starts pod, sees secretKeyRef
t=2m     Kubelet                  Asks API Server for secret
t=2m     API Server               Reads from etcd → returns plain values
t=2m     Kubelet                  Injects env vars into container
t=2m     App                      Reads os.getenv("DB_PASSWORD") → "SuperSecret123!"
         ─── APP RUNNING ───
```
