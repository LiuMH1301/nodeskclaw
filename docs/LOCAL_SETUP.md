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

## Step 2: Configure DATABASE_URL

The backend `.env` ships with placeholder values. Set the correct local PostgreSQL connection:

```bash
# In nodeskclaw-backend/.env, change:
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:5432/nodeskclaw

# To:
DATABASE_URL=postgresql+asyncpg://nodeskclaw:nodeskclaw@localhost:5432/nodeskclaw
```

These credentials match the docker-compose postgres defaults.

## Step 3: Expose PostgreSQL Port to Host

`docker-compose.yml` does not expose PostgreSQL port 5432 to the host — it's only accessible between containers. For local dev with `dev.sh`, create an override file:

```bash
cat > docker-compose.override.yml <<'EOF'
services:
  postgres:
    ports:
      - "5432:5432"
EOF
```

Then start only PostgreSQL:

```bash
docker compose up -d postgres
```

> **Note:** The `DESKCLAW_VERSION` warnings are harmless when starting only postgres.

## Step 4: Fix LLM Proxy URL for kind

`dev.sh` sets `LLM_PROXY_INTERNAL_URL` to `localhost:4511`, but K8s pods inside kind can't reach `localhost` on the host. Change it to `host.docker.internal`:

Edit `dev.sh`:

```bash
# Line ~271: Change localhost to host.docker.internal
export LLM_PROXY_INTERNAL_URL="http://host.docker.internal:4511"
```

Without this fix, AI employees will connect and appear healthy, but all LLM requests will fail with "network connection error" because the pod's `openclaw.json` gets `localhost:4511` as the LLM endpoint.

## Step 5: Fix PVC Access Mode for kind

kind's `local-path` StorageClass only supports `ReadWriteOnce`. Edit `nodeskclaw-backend/app/services/k8s/resource_builder.py`:

```python
# Line ~137: Change ReadWriteMany to ReadWriteOnce
access_modes=["ReadWriteOnce"],  # was "ReadWriteMany"
```

This is required for local kind clusters. Production clusters with NFS/shared storage may use `ReadWriteMany`.

## Step 6: Create a kind Cluster

```bash
kind create cluster
```

Verify it's running:

```bash
kubectl cluster-info --context kind-kind
kubectl get nodes --context kind-kind
```

## Step 7: Build and Load the OpenClaw Image

The default image registry (`nodesk-center-cn-beijing.cr.volces.com`) is not publicly accessible. Build the image locally instead.

**Important:** On Apple Silicon, do NOT use `--platform linux/amd64` — kind runs arm64 nodes natively.

```bash
cd nodeskclaw-artifacts/openclaw-image

# Build with the latest OpenClaw version (2026.4.2+ required for MCP gene support)
docker build \
  --build-arg OPENCLAW_VERSION=2026.4.2 \
  --build-arg IMAGE_VERSION=v2026.4.2 \
  -t nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw:v2026.4.2 .

# Load into kind
kind load docker-image nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw:v2026.4.2 --name kind
```

The UI image dropdown is populated from the remote registry, which may only list older versions (e.g., `v2026.3.13`). Tag your local build to match:

```bash
docker tag nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw:v2026.4.2 \
           nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw:v2026.3.13
kind load docker-image nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw:v2026.3.13 --name kind
```

Verify the image is loaded:

```bash
docker exec kind-control-plane crictl images | grep deskclaw
```

> **Kind image caching gotcha:** `kind load` will NOT overwrite an existing tag in containerd. If you need to replace an image, first remove the old one:
> ```bash
> docker exec kind-control-plane ctr -n k8s.io images delete \
>   nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw:v2026.3.13
> kind load docker-image nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw:v2026.3.13 --name kind
> ```

## Step 8: Start the Backend and Portal

```bash
cd nodeskclaw  # back to project root
./dev.sh
```

This starts:
- **Backend API** at `http://localhost:4510`
- **LLM Proxy** at `http://localhost:4511`
- **Portal** at `http://localhost:4517`

> **Note:** PostgreSQL must already be running (Step 3). `dev.sh` does not start it.

Default login: `admin` (password is printed in the backend startup logs on first run).

## Step 9: Add the kind Cluster in the UI

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

## Step 10: Create an AI Employee

1. Navigate to create a new AI employee
2. Select **OpenClaw** as the engine type
3. Choose image version (the UI lists tags from the remote registry; select whichever tag you built and loaded into kind in Step 7)
4. Configure an LLM provider (required for the AI employee to function)
5. Deploy
6. Wait for the pod to show **Running** in the Overview page

## Step 11: Create a Cyber Workspace

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

### AI employee not responding after backend restart
Each AI employee maintains a persistent WebSocket tunnel to the backend. When the backend restarts, all tunnel connections are dropped. The pods detect this and reconnect with exponential backoff (1s, 2s, 4s, ... up to 30s), but during this window messages sent to an agent will be silently lost (sent to a dead-letter queue with no retry).

After restarting the backend:
1. **Wait ~30 seconds** for all pods to reconnect their tunnels
2. Check the Overview page — agents should show **healthy** once tunnels are re-established
3. If an agent still appears unreachable, delete the pod to force a fresh connection:
```bash
kubectl delete pod <pod-name> -n <namespace> --context kind-kind
```

> **Note:** The tunnel is between the pod and the backend process, not the browser. Refreshing the browser or logging in again does not affect tunnels. Only a backend restart breaks them.

### AI employee shows "Running (Unreachable)" or "Disconnected"
The tunnel hasn't connected. Possible causes:
1. **Not added to a workspace yet** — the tunnel client only activates after workspace assignment
2. **Backend was restarted** — see "AI employee not responding after backend restart" above
3. **NetworkPolicy blocking egress** — ensure `EGRESS_DENY_CIDRS` is empty and `EGRESS_ALLOW_PORTS` includes `4510,4511` in `.env` (see Step 1)
4. **`channels` section missing from openclaw.json** — the tunnel client reads its connection config from `channels.nodeskclaw.accounts` in `openclaw.json`, NOT from environment variables. If the config file was regenerated (e.g., after PVC wipe, truncation, or manual deletion), this section is lost because the entrypoint template doesn't include it.

To fix, remove the AI employee from the workspace in the portal, then re-add it. This triggers `deploy_nodeskclaw_channel_plugin` which writes the complete config including:
- `channels.nodeskclaw.accounts.default` — with `apiUrl`, `workspaceId`, `instanceId`, and `apiToken`
- `gateway.http.endpoints.chatCompletions` — enables the HTTP endpoint the backend uses to send messages

Without `chatCompletions` enabled, the tunnel connects but messages fail with "Local OpenClaw API returned 404".

Verify the config was written:
```bash
kubectl exec <pod-name> -n <namespace> --context kind-kind -- cat /root/.openclaw/openclaw.json | python3 -m json.tool
```
Check for both the `channels.nodeskclaw.accounts.default` section and `gateway.http.endpoints.chatCompletions.enabled: true`.

### openclaw.json regenerated — AI employee broken after PVC wipe
`openclaw.json` on the PVC is the **single source of truth** for all runtime config. The entrypoint template only contains minimal gateway settings. When this file is regenerated (PVC wipe, truncation, manual deletion), the following backend-managed sections are lost:

| Section | Purpose | Symptom when missing |
|---------|---------|---------------------|
| `channels.nodeskclaw.accounts` | Tunnel connection config | "Disconnected" in portal |
| `gateway.http.endpoints.chatCompletions` | HTTP message endpoint | "Local OpenClaw API returned 404" |
| `models.providers` | LLM proxy routing | "No API key found for provider" |
| `agents.defaults.model` | Default chat model | Falls back to `anthropic/claude-opus-4-6` |
| `mcp.servers` | Gene MCP servers | Gene tools unavailable |
| `tools.allow` | Tool whitelist | Tools blocked |
| `skills.load.extraDirs` | Skill discovery | Skills not loaded |

**To recover all sections at once:**
1. Remove the AI employee from the workspace, then re-add it (writes channels + gateway config)
2. Go to the AI employee's LLM settings in the portal and click Save (writes models.providers + agent model)
3. Re-install any genes from the marketplace (writes mcp.servers + tools.allow)

Alternatively, delete the PVC and redeploy the AI employee from scratch — the backend writes all config sections during initial deployment.

### Pod fails with "Insufficient memory" / FailedScheduling
Kind runs a single node. Deploying multiple AI employees can exhaust available memory. Check allocation:
```bash
kubectl describe node --context kind-kind | grep -A 5 "Allocated resources"
```
To free memory, scale down or delete idle AI employee deployments:
```bash
# List running AI employee pods
kubectl get pods -A --context kind-kind | grep nodeskclaw-default

# Scale down an idle instance
kubectl scale deployment <name> -n <namespace> --replicas=0 --context kind-kind

# Or delete the entire namespace to reclaim all resources
kubectl delete namespace <namespace> --context kind-kind
```

### MCP gene tools fail with "Connection closed"
The gene installation deploys script files to the PVC but does **not** run `npm install` for Node.js-based MCP servers (e.g., `social-media-browser`). The MCP server crashes on startup because `node_modules/` is missing.

Fix by installing dependencies manually inside the pod:
```bash
kubectl exec <pod-name> -n <namespace> --context kind-kind -- \
  npm install --prefix /root/.deskclaw/tools/social-media-browser/
```

No pod restart needed — OpenClaw retries the MCP server on the next tool invocation. For Python-based MCP servers (e.g., `media-generator`), dependencies are pre-installed at `/opt/gene-python-deps` in the custom image (see Step 7).

### Pod crashes with "Unrecognized key: mcpServers"
The MCP gene (e.g., `social-media-browser`, `media-generator`) wrote `mcpServers` to `openclaw.json` but the OpenClaw version doesn't support it. This requires:
1. **OpenClaw 2026.4.2+** — rebuild the image with `--build-arg OPENCLAW_VERSION=2026.4.2` (see Step 7)
2. **Backend fix** — the config key must be `mcp.servers` (nested), not `mcpServers` (top-level). Ensure `openclaw_gene_install_adapter.py` writes to `config["mcp"]["servers"]`.

To recover a crashing pod, remove the invalid config key from the PVC:
```bash
# Scale down the deployment
kubectl scale deployment <name> -n <namespace> --replicas=0 --context kind-kind

# Launch a debug pod to access the PVC
kubectl run debug-pvc -n <namespace> --context kind-kind \
  --image=busybox --restart=Never \
  --overrides='{"spec":{"containers":[{"name":"debug","image":"busybox","command":["sleep","300"],"resources":{"requests":{"cpu":"100m","memory":"64Mi"},"limits":{"cpu":"100m","memory":"64Mi"}},"volumeMounts":[{"name":"data","mountPath":"/data"}]}],"volumes":[{"name":"data","persistentVolumeClaim":{"claimName":"<pvc-name>"}}]}}'

# Delete the config file (entrypoint will regenerate it)
kubectl exec debug-pvc -n <namespace> --context kind-kind -- rm /data/.openclaw/openclaw.json

# Clean up and restart
kubectl delete pod debug-pvc -n <namespace> --context kind-kind
kubectl scale deployment <name> -n <namespace> --replicas=1 --context kind-kind
```
Then re-install the MCP gene from the portal to trigger a fresh config sync.

### Database migration fails on startup
If `./dev.sh` shows `cannot connect to '<host>:5432/nodeskclaw'`:
1. **PostgreSQL not running** — run `docker compose up -d postgres`
2. **DATABASE_URL is a placeholder** — check `nodeskclaw-backend/.env` has real credentials (see Step 2)
3. **Port not exposed** — ensure `docker-compose.override.yml` exists with postgres port mapping (see Step 3)
