# Local Development Setup (macOS Apple Silicon)

Complete guide to get DeskClaw running locally on a fresh Mac with Apple Silicon.

## Prerequisites

| Tool | Install |
|------|---------|
| Docker Desktop | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| Node.js 22+ | `brew install node` |
| Python 3.12+ | `brew install python@3.12` |
| uv | `brew install uv` |
| kind | `brew install kind` |
| kubectl | `brew install kubectl` |

Make sure **Docker Desktop is running** before proceeding.

## Step 1: Clone and Configure Environment

```bash
git clone <repo-url> nodeskclaw
cd nodeskclaw
```

Edit `nodeskclaw-backend/.env` — set the `AGENT_API_BASE_URL` so K8s pods can reach your local backend:

```bash
# Find this line:
# AGENT_API_BASE_URL=http://host.docker.internal:4510/api/v1

# Uncomment it to:
AGENT_API_BASE_URL=http://host.docker.internal:4510/api/v1
```

> **Important:** Do NOT run `cp .env.example .env` after this point — it will overwrite your changes.

## Step 2: Fix LLM Proxy URL for kind

`dev.sh` sets `LLM_PROXY_INTERNAL_URL` to `localhost:4511`, but K8s pods inside kind can't reach `localhost` on the host. Change it to `host.docker.internal`:

Edit `dev.sh`:

```bash
# Line ~271: Change localhost to host.docker.internal
export LLM_PROXY_INTERNAL_URL="http://host.docker.internal:4511"
```

Without this fix, AI employees will connect and appear healthy, but all LLM requests will fail with "network connection error" because the pod's `openclaw.json` gets `localhost:4511` as the LLM endpoint.

## Step 3: Fix PVC Access Mode for kind

kind's `local-path` StorageClass only supports `ReadWriteOnce`. Edit `nodeskclaw-backend/app/services/k8s/resource_builder.py`:

```python
# Line ~137: Change ReadWriteMany to ReadWriteOnce
access_modes=["ReadWriteOnce"],  # was "ReadWriteMany"
```

This is required for local kind clusters. Production clusters with NFS/shared storage may use `ReadWriteMany`.

## Step 4: Create a kind Cluster

```bash
kind create cluster
```

Verify it's running:

```bash
kubectl cluster-info --context kind-kind
kubectl get nodes --context kind-kind
```

## Step 5: Build and Load the OpenClaw Image

The default image registry (`nodesk-center-cn-beijing.cr.volces.com`) is not publicly accessible. Build the image locally instead.

**Important:** On Apple Silicon, do NOT use `--platform linux/amd64` — kind runs arm64 nodes natively.

```bash
cd nodeskclaw-artifacts/openclaw-image

# Build the image (uses the default tag from the Dockerfile)
docker build -t nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw:v2026.3.24 .

# Load into kind
kind load docker-image nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw:v2026.3.24
```

If the UI offers a different version (e.g., `v2026.3.13`), tag and load that too:

```bash
docker tag nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw:v2026.3.24 \
           nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw:v2026.3.13
kind load docker-image nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw:v2026.3.13
```

Verify the image is loaded:

```bash
docker exec kind-control-plane crictl images | grep deskclaw
```

## Step 6: Start the Backend and Portal

```bash
cd nodeskclaw  # back to project root
./dev.sh --docker-pg
```

This starts:
- **PostgreSQL** in Docker (auto-configured)
- **Backend API** at `http://localhost:4510`
- **LLM Proxy** at `http://localhost:4511`
- **Portal** at `http://localhost:4517`

Default login: `admin` (password is printed in the backend startup logs on first run).

## Step 7: Add the kind Cluster in the UI

1. Open `http://localhost:4517`
2. Log in with the admin account
3. Go to cluster management settings
4. Click "Add Cluster" and select **K8s**
5. Paste your kind kubeconfig:

```bash
# Get the kubeconfig to paste into the UI
kind get kubeconfig
```

6. Click **Test Connection** to verify connectivity

## Step 8: Create an AI Employee

1. Navigate to create a new AI employee
2. Select **OpenClaw** as the engine type
3. Choose image version **v2026.3.24** (or whichever version you built)
4. Configure an LLM provider (required for the AI employee to function)
5. Deploy
6. Wait for the pod to show **Running** in the Overview page

## Step 9: Create a Cyber Workspace

The AI employee won't connect to the backend until it's added to a workspace:

1. Create a new Cyber Workspace (e.g., "Marketing")
2. Add the AI employee to the workspace
3. This triggers the channel plugin deployment and instance restart
4. After restart, the tunnel connects and status becomes **healthy**

> **Note:** If the pod enters CrashLoopBackOff after being added to a workspace, see the
> "CrashLoopBackOff after adding to workspace" troubleshooting section below.

## Troubleshooting

### "Cannot connect to the Docker daemon"
Open Docker Desktop first. Wait for it to fully start before running any commands.

### "AGENT_API_BASE_URL is currently localhost"
Your `.env` was overwritten. Re-edit `nodeskclaw-backend/.env` and set:
```
AGENT_API_BASE_URL=http://host.docker.internal:4510/api/v1
```
The backend auto-reloads, no restart needed.

### Pod fails with "ImagePullBackOff"
The image tag in the UI doesn't match what's loaded in kind. Check loaded images:
```bash
docker exec kind-control-plane crictl images | grep deskclaw
```
Then tag and load the missing version (see Step 4).

### PVC fails with "NodePath only supports ReadWriteOnce"
You missed Step 3. Change `ReadWriteMany` to `ReadWriteOnce` in `resource_builder.py`.

### Cluster shows "Disconnected"
Click **Test Connection** in the cluster settings. New clusters start as disconnected by design.

### Backend `.env` keeps reverting
Do NOT run `cp .env.example .env` after configuring. Only run `./dev.sh --docker-pg` to restart.

### CrashLoopBackOff after adding to workspace
The dingtalk channel plugin may fail to fully deploy, leaving an incomplete directory that crashes OpenClaw.
Check the pod logs:
```bash
kubectl logs <pod-name> -n <namespace> --context kind-kind --previous
```
If you see `plugin manifest not found: .../openclaw-channel-dingtalk/openclaw.plugin.json`, fix it:
```bash
# Find the PVC path
PV=$(kubectl get pvc -n <namespace> --context kind-kind -o jsonpath='{.items[0].spec.volumeName}')

# Remove the incomplete plugin directory
docker exec kind-control-plane rm -rf /var/local-path-provisioner/${PV}_<namespace>_*-root-data/.openclaw/extensions/openclaw-channel-dingtalk

# Delete the crashing pod so K8s recreates it immediately
kubectl delete pod <pod-name> -n <namespace> --context kind-kind
```

### AI employee responds with "LLM request failed: network connection error"
You missed Step 2. The pod's `openclaw.json` has `localhost:4511` as the LLM endpoint, which is unreachable from inside the pod. Fix `dev.sh` to use `host.docker.internal:4511`, restart the backend, then restart the pods. If the pods already have the old config on their PVC, you need to either:
- Patch the config directly: `kubectl exec -n <namespace> <pod> --context kind-kind -- sed -i 's|http://localhost:4511|http://host.docker.internal:4511|g' /root/.openclaw/openclaw.json` then delete the pod
- Or delete the PVC and redeploy the AI employee

### AI employee shows "Running (Unreachable)"
The tunnel hasn't connected. Possible causes:
1. **Not added to a workspace yet** — the tunnel client only activates after workspace assignment
2. **NetworkPolicy blocking egress** — ensure `EGRESS_DENY_CIDRS` is empty and `EGRESS_ALLOW_PORTS` includes `4510,4511` in `.env` (see Step 1)
