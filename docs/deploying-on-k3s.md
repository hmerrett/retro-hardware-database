# Deploying to a Civo K3s cluster

Notes from putting this app on a three-node Civo K3s cluster at
`pocketradioshow.com`. Written for whoever does it next — the awkward bits are
the ones nobody warns you about, so they are the ones written down here.

**This is a test deployment.** Where it departs from the Compose stack, it says
so, and the differences are listed at the end. Nothing here is committed with
secrets in it; every credential is read back out of the cluster.

---

## What is running

| Namespace | What |
|---|---|
| `rhdb` | the app (`api`), MariaDB (`db`), three PVCs, Ingress + Let's Encrypt cert |
| `rhdb-build` | a private registry and a BuildKit builder, used to build the image |
| `cert-manager` | cert-manager and a `letsencrypt-prod` ClusterIssuer |
| `kube-system` | Traefik — **already there**, installed by Civo |

The site is at <https://pocketradioshow.com>. Browsing is public; editing needs
the login.

### Reading the credentials back

They were generated at deploy time and live only in the cluster:

```bash
kubectl -n rhdb get secret rhdb-secrets -o jsonpath='{.data.RHDB_AUTH_USER}' | base64 -d; echo
kubectl -n rhdb get secret rhdb-secrets -o jsonpath='{.data.RHDB_AUTH_PASSWORD}' | base64 -d; echo
```

---

## The five things that will bite you

### 1. Civo ships Traefik, but not Traefik's CRDs

`kubectl get pods -n kube-system` shows a `traefik` **DaemonSet on the host
network** (v2.9.4), so ports 80 and 443 answer on every node's IP directly.
There is no `LoadBalancer` Service and no Civo load balancer in front — which is
why DNS can point straight at a node IP.

Two consequences:

- **There is no `IngressClass` object.** Do not set `ingressClassName` on your
  Ingress; leave it out and Traefik's `kubernetesingress` provider picks it up.
  Setting a class name that does not exist gets you a silently unrouted Ingress.
- **`Middleware` and the other Traefik CRDs are not installed**, even though
  `--providers.kubernetescrd` is enabled. So the usual recipes for basic auth,
  security headers or a redirect middleware do not work out of the box. You
  either install the CRDs yourself or find another way (both used below).

### 2. Your Mac is arm64 and the nodes are amd64

Civo's nodes are amd64 Alpine. Building on an Apple Silicon Mac gives you an
arm64 image that the nodes cannot run, and `--platform linux/amd64` under
emulation is painfully slow for anything that compiles (Pillow, reportlab).

This deployment **builds inside the cluster instead**: a `moby/buildkit` pod
does the build natively on amd64 and pushes to a registry in the same cluster.
No Docker Desktop, no Docker Hub account, no QEMU.

```bash
# Package only what the Dockerfile actually COPYs
cd api
tar czf /tmp/api-context.tgz Dockerfile requirements.txt app alembic.ini \
    migrations entrypoint.sh fix-volumes.sh

BK=$(kubectl get pod -n rhdb-build -l app=buildkit -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n rhdb-build "$BK" -- mkdir -p /workspace/api
kubectl cp /tmp/api-context.tgz "rhdb-build/$BK:/workspace/api-context.tgz"
kubectl exec -n rhdb-build "$BK" -- tar xzf /workspace/api-context.tgz -C /workspace/api

kubectl exec -n rhdb-build "$BK" -- buildctl build \
  --frontend dockerfile.v0 \
  --local context=/workspace/api \
  --local dockerfile=/workspace/api \
  --output type=image,name=registry.74-220-26-37.sslip.io/rhdb-api:v2,push=true
```

Then roll it out:

```bash
kubectl -n rhdb set image deployment/api api=registry.74-220-26-37.sslip.io/rhdb-api:v2
kubectl -n rhdb rollout status deployment/api
```

Bump the tag every time. Reusing a tag leaves the node's cached copy in place and
you will swear the build did nothing.

**Check what you are building from.** The context is a tarball of your working
tree, not of `main`, so whatever branch is checked out is what ships — silently,
and with no commit recorded anywhere in the cluster. `git status` before you
build, and consider tagging the image after the commit it came from rather than
`v1`, `v2`.

### 3. containerd will not pull from a plain-HTTP registry — and fixing that
### properly needs root on every node

This is the real obstacle to an in-cluster registry. containerd is not Docker:
there is no "insecure registry" default for `localhost`, and no amount of
Kubernetes YAML changes its mind. The documented fix is to write
`/etc/rancher/k3s/registries.yaml` on **every node** and restart K3s — which
needs host access, and restarts containerd and so every pod on that node.

**The way round it: give the registry a name that already resolves to the
cluster, and get it a real certificate.** Then containerd trusts it like any
other registry and there is nothing to configure on the nodes at all.

[sslip.io](https://sslip.io) answers `<anything>.74-220-26-37.sslip.io` with
`74.220.26.37`. That is this cluster's node IP, so a Let's Encrypt HTTP-01
challenge validates against Traefik with **no DNS record to create**:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: registry
  namespace: rhdb-build
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  rules:
    - host: registry.74-220-26-37.sslip.io      # no ingressClassName — see §1
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service: {name: registry, port: {number: 5000}}
  tls:
    - hosts: [registry.74-220-26-37.sslip.io]
      secretName: registry-tls
```

That name is on the public internet, so the registry carries its **own**
htpasswd auth rather than a Traefik middleware (which would need the CRDs from
§1). `registry:2` only accepts **bcrypt**, so generate it with `htpasswd -B`:

```bash
htpasswd -nbB builder "$PASSWORD" > htpasswd.txt
kubectl create secret generic registry-htpasswd -n rhdb-build --from-file=htpasswd=htpasswd.txt
```

The registry deployment then wants `REGISTRY_AUTH=htpasswd`,
`REGISTRY_AUTH_HTPASSWD_REALM`, `REGISTRY_AUTH_HTPASSWD_PATH=/auth/htpasswd`
and — because it sits behind a proxy that terminates TLS —
`REGISTRY_HTTP_RELATIVEURLS=true`, without which blob redirects point at the
wrong scheme.

BuildKit needs those credentials at `/root/.docker/config.json` in its own pod
(`kubectl exec … mkdir -p /root/.docker` first — `kubectl cp` will not create
the parent). The app pulls with an `imagePullSecret` of type
`kubernetes.io/dockerconfigjson` in the `rhdb` namespace.

> If you would rather not expose a registry publicly at all, the alternatives
> are the `registries.yaml` route above (needs host access) or building
> somewhere else and pushing to GHCR. The sslip.io trick is what lets this run
> end to end with nothing but a kubeconfig.

### 4. Volumes come up owned by root, and neither container runs as root

`civo-volume` is the default StorageClass: **ReadWriteOnce block storage**,
`WaitForFirstConsumer`, reclaim policy `Delete`. A freshly provisioned volume is
owned by root, but:

- MariaDB runs as uid 999
- this app runs as `appuser`, uid 10001 (see `api/Dockerfile`)

Under Compose the `api-init` service runs `fix-volumes.sh` as root to sort this
out. In Kubernetes the equivalent is one line — `fsGroup` on the pod, which
makes the mount group-owned and setgid:

```yaml
spec:
  securityContext:
    fsGroup: 999      # db
    # fsGroup: 10001  # api
```

Miss it and MariaDB fails to initialise its datadir, or the app cannot write
photographs, both with errors that do not obviously say "ownership".

Because the volumes are **ReadWriteOnce**, both Deployments use
`strategy: {type: Recreate}`. A `RollingUpdate` deadlocks: the new pod waits
for a volume the old pod is still holding. This also means **you cannot scale
`api` past one replica** as it stands — `images/` and `files/` are on RWO block
storage, not a shared filesystem.

Volume attach is not instant. Expect a minute or so of `FailedAttachVolume`
warnings on first boot; they clear themselves.

### 5. Ordering: migrations run before the app does

`api/entrypoint.sh` runs `alembic upgrade head` and only then starts uvicorn.
If MariaDB is not ready the pod crash-loops until it is. An init container makes
it deterministic:

```yaml
initContainers:
  - name: wait-for-db
    image: busybox:1.36
    command: ["sh", "-c", "until nc -z db 3306; do sleep 2; done"]
```

Give the app a **`startupProbe`** with a generous `failureThreshold` (60 × 5s
here) rather than a slack `livenessProbe`. A fresh database means all 38
migrations run before the first byte is served, and a tight liveness probe will
kill the pod halfway through.

---

## TLS

cert-manager via Helm, with a `letsencrypt-prod` ClusterIssuer solving HTTP-01
through Traefik. The solver Ingress needs no class, same as §1:

```yaml
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    privateKeySecretRef: {name: letsencrypt-prod-account}
    solvers:
      - http01:
          ingress: {}
```

No contact email is registered — Let's Encrypt treats it as optional and this is
a test install. **On anything real, add `email:`** or you get no warning when
renewal starts failing.

Traefik on its own serves the site on port 80 as well as 443, which is wrong
when `RHDB_BASE_URL` is `https://…`. Caddy did the redirect in the Compose
stack; here it is two flags on the Civo DaemonSet:

```bash
kubectl patch ds traefik -n kube-system --type=json -p '[
  {"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--entrypoints.web.http.redirections.entryPoint.to=websecure"},
  {"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--entrypoints.web.http.redirections.entryPoint.scheme=https"}
]'
```

**This does not break renewals**, which is the obvious worry — Let's Encrypt
follows redirects during HTTP-01 and does not validate the certificate on the
target. Verified here by deleting the issued secret and watching cert-manager
re-issue cleanly with the redirect in place. Worth re-verifying if you change
the redirect, because the failure would otherwise surface silently at day 60.

Note this patches a Civo-managed resource. If Civo ever reconciles the
DaemonSet the flags go and the redirect quietly stops; the site keeps working.

### DNS

Only the **apex** `pocketradioshow.com` points at the cluster.
`www.pocketradioshow.com` is a CNAME to an LCN web-forward on entirely different
addresses, so the certificate deliberately covers the apex only. Adding `www` to
the Ingress before repointing that record would fail HTTP-01 and block the
whole certificate, apex included.

---

## How this differs from the Compose stack

Worth knowing before you treat it as equivalent:

- **No Caddy.** Traefik terminates TLS instead, so the `header` block in
  `caddy/Caddyfile` is **not applied**: no HSTS, no `nosniff`, no
  `Referrer-Policy`, no `X-Frame-Options`. Restoring them needs the Traefik
  CRDs from §1 plus a `Middleware`, and is the first thing to fix if this
  becomes anything other than a test.

  The **Content-Security-Policy survives**, because it was never Caddy's: the
  app sends it itself and the suite holds it to what the templates actually do
  (ADR-0021). That is the split working as intended — a policy about the app's
  own markup travels with the app, and only the transport headers are lost with
  the proxy that sent them.
- **No GoAccess.** It parses Caddy's JSON access log off a shared volume, and
  there is no Caddy. `/traffic` has nothing to show.
- **No MCP server.** `mcp/` is not deployed. Build and deploy it the same way
  as `api` if you want it, with `API_BASE_URL=http://api:8000`.
- **No `branding/` mount.** `common.branded()` falls back to the shipped files
  when the directory is absent, so this is harmless — but this installation's
  own logo, icons and watermark are not in place. Mount a ConfigMap (or a PVC)
  at `/app/branding` read-only to restore them.
- **No backups.** The PVCs are Civo block volumes with reclaim policy
  `Delete` — **deleting the cluster deletes the database**. There is no
  `mysqldump` schedule here.
- **`RHDB_OPEN` is unset** and credentials are set, which is the intended
  pairing: the app is not open, so it neither warns at startup nor banners the
  pages (ADR-0019).

---

## Rebuilding from scratch

Order matters, because each step needs the one before it:

1. `helm upgrade --install cert-manager jetstack/cert-manager -n cert-manager --create-namespace --set crds.enabled=true --wait`
2. `ClusterIssuer letsencrypt-prod`
3. registry + PVC + htpasswd secret + Ingress — **wait for `registry-tls` to go
   `READY=True`** before building, or the push has nothing to trust
4. BuildKit, then the build and push (§2)
5. `rhdb-secrets`, `registry-creds`, MariaDB, then the app and its Ingress

Useful checks:

```bash
kubectl get certificate -A                    # READY must be True
kubectl get challenges -A                     # empty once validated
kubectl -n rhdb logs deployment/api           # migrations, then uvicorn
kubectl -n rhdb get events --field-selector type=Warning
```

Let's Encrypt's production rate limit is 5 duplicate certificates per week. If
you expect to tear this down and rebuild repeatedly, point the ClusterIssuer at
`https://acme-staging-v02.api.letsencrypt.org/directory` while you iterate —
but note that a staging certificate is **not** trusted by containerd either, so
the registry trick in §3 needs the production issuer to work at all.
