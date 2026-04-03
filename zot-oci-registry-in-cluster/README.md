# Zot OCI Registry — Deployment Guide

## Overview

This guide covers deploying [Zot](https://zotregistry.dev) as an internal OCI registry on Kubernetes with TLS termination via kgateway (Gateway API). Two access paths are documented:

- **External** — TLS via a publicly accessible hostname (Let's Encrypt), used for pushing images and accessing the Web UI
- **Internal** — TLS via a private CA, accessed directly by containerd within the cluster via a internal-lb cidr LoadBalancer IP

## Prerequisites

- kgateway v2.2.2+ installed (see [Dependencies](#dependencies))
- cert-manager installed with the following `ClusterIssuers` available (see [Dependencies](#dependencies)):
  - `letsencrypt-prod` — for external TLS
  - `selfsigned-cluster-issuer` — used to bootstrap the internal CA
  - `internal-ca-issuer` — for internal TLS (see [Internal CA Bootstrap](#internal-ca-bootstrap))
- Choose an unused VIP from the internal_lb CIDR pool
- Helm 3.x
- `kubectl` configured against the target cluster
- `cwic` Coreweave CLI

---

## Dependencies

### kgateway

Installs the Gateway API CRDs (standard channel) and the kgateway controller.

```bash
# Gateway API CRDs (standard channel)
kubectl apply -f \
  https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.4.0/standard-install.yaml

# kgateway CRDs
helm upgrade -i kgateway-crds \
  oci://cr.kgateway.dev/kgateway-dev/charts/kgateway-crds \
  --create-namespace \
  --namespace kgateway-system \
  --version v2.2.2

# kgateway controller
helm upgrade -i kgateway \
  oci://cr.kgateway.dev/kgateway-dev/charts/kgateway \
  --namespace kgateway-system \
  --version v2.2.2
```

### cert-manager

Install cert-manager using the CoreWeave Helm chart with cluster issuers pre-configured. The values file enables `letsencrypt-prod`, `letsencrypt-staging`, and `selfsigned-cluster-issuer` with Gateway API HTTP-01 challenge support.

```bash
helm repo add coreweave https://charts.core-services.ingress.coreweave.com

helm repo update

# Initial install without values
helm -n kube-system upgrade --install cert-manager coreweave/cert-manager

# Apply with cluster issuer values
helm -n kube-system upgrade --install cert-manager coreweave/cert-manager \
  -f files/cert-manager-values.yaml
```

### Verify

```bash
kubectl get clusterissuer
NAME                        READY   AGE
letsencrypt-prod            True    165m
letsencrypt-staging         True    165m
selfsigned-cluster-issuer   True    165m

kubectl get pods -n kgateway-system
NAME                                    READY   STATUS    RESTARTS   AGE
kgateway-54c457cc5c-bfwx9               1/1     Running   0          168m

kubectl get gatewayclass
NAME       CONTROLLER              ACCEPTED   AGE
kgateway   kgateway.dev/kgateway   True       169m
```

---

## Zot Helm Install

Generate htpasswd credentials before installing:

```bash
# Install htpasswd if needed: apt install apache2-utils
htpasswd -nbB <ZOT_USERNAME> <ZOT_PASSWORD>
# Copy the output — this is <ZOT_HTPASSWD_STRING>
```

```bash
helm repo add zotregistry https://zotregistry.dev/helm-charts
helm repo update

helm -n zot-registry upgrade --install zot zotregistry/zot \
  --version 0.1.98 \
  --create-namespace \
  -f files/zot-values.yaml
```

### Placeholders (`files/zot-values.yaml`)

| Placeholder | Description |
|---|---|
| `<ZOT_USERNAME>` | Registry admin username — set in `accessControl.adminPolicy.users` |
| `<ZOT_HTPASSWD_STRING>` | Output of `htpasswd -nbB <ZOT_USERNAME> <ZOT_PASSWORD>` — set in `secretFiles.htpasswd` |
| `<S3_REGION>` | Object storage bucket region (e.g. `us-east-14a`) |
| `<S3_BUCKET_NAME>` | AI Object Storage bucket name |
| `<S3_ACCESS_KEY_ID>` | Object storage access key ID |
| `<S3_SECRET_KEY>` | Object storage secret key |

---

## zot-infra Infrastructure Chart

The internal CA, both Gateways, and the containerd DaemonSet are all managed by the `zot-infra` Helm chart. Fill in `zot-infra/values.yaml` with the values described in each section below, then install once:

```bash
helm -n zot-registry upgrade -i zot-infra ./zot-infra \
  -f ./zot-infra/values.yaml
```

---

## Internal CA Bootstrap

Creates a self-signed CA and a `ClusterIssuer` backed by it. All internal leaf certs are signed by this CA. cert-manager will automatically retry issuance of the internal leaf certificate once the `ClusterIssuer` reaches `READY=True` — no separate install step is needed.

### Values (`zot-infra/values.yaml`)

| Key | Description |
|---|---|
| `ca.certificateName` | Name of the cert-manager Certificate resource for the CA |
| `ca.secretName` | Secret where the CA key/cert are stored — referenced by the ClusterIssuer and DaemonSet |
| `ca.issuerName` | Name of the ClusterIssuer backed by this CA |
| `ca.bootstrapIssuer` | Pre-existing ClusterIssuer used to self-sign the CA (must already exist) |
| `namespaces.certManager` | Namespace where cert-manager is installed (default: `kube-system`) |

### Verify

```bash
# Wait for READY=True before proceeding
kubectl get clusterissuer internal-ca-issuer
NAME                 READY   AGE
internal-ca-issuer   True    145m
```

---

## External Gateway (Let's Encrypt TLS)

Exposes zot on a public hostname with TLS terminated at the Gateway using a Let's Encrypt certificate managed by cert-manager. This endpoint is used for:

- **Pushing images** from external CI/CD pipelines or developer machines via `docker push` / `skopeo copy`
- **Accessing the Zot Web UI** at `https://registry.<ORG_ID-CLUSTER_NAME>.coreweave.app`

### Values (`zot-infra/values.yaml`)

| Key | Description |
|---|---|
| `externalGateway.clusterOrgHostname` | ORG ID and CKS Cluster Name (e.g. `cwxxx-cluster03`) |
| `namespaces.kgateway` | Namespace where kgateway is installed (default: `kgateway-system`) |
| `namespaces.zot` | Namespace where zot is installed (default: `zot-registry`) |

### Verify

```bash
kubectl get gateway zot-external-gateway -n kgateway-system
NAME                   CLASS      ADDRESS         PROGRAMMED   AGE
zot-external-gateway   kgateway   166.xx.xx.xx   True         106m

kubectl get certificate -n kgateway-system
NAME                     READY   SECRET                     AGE
zot-public-cert-secret   True    zot-public-cert-secret     106m

kubectl get httproute -n zot-registry
NAME                 HOSTNAMES                                          AGE
zot-external-route   ["registry.ORG_ID-CLUSTER_NAME.coreweave.app"]   106m
```

### Push an image via the external endpoint

```bash
# Log in
docker login registry.<ORG_ID-CLUSTER_NAME>.coreweave.app \
  -u <ZOT_USERNAME> -p <ZOT_PASSWORD>

# Tag and push
docker tag myapp:latest \
  registry.<ORG_ID-CLUSTER_NAME>.coreweave.app/myapp:latest

docker push registry.<ORG_ID-CLUSTER_NAME>.coreweave.app/myapp:latest
```

### Web UI

Navigate to `https://registry.<ORG_ID-CLUSTER_NAME>.coreweave.app` in a browser to browse repositories, tags, and image details via the Zot UI.

---

## Internal Gateway (Private CA TLS + internal-lb VIP)

Exposes zot on a fixed internal LoadBalancer IP for direct in-cluster pulls by containerd. TLS is terminated at the Gateway using a cert with an IP SAN matching the internal-lb IP.

### Values (`zot-infra/values.yaml`)

| Key | Description |
|---|---|
| `internalGateway.lbIP` | Fixed internal-lb IP for the LoadBalancer Service (e.g. `10.16.12.10`) |
| `namespaces.kgateway` | Namespace where kgateway is installed (default: `kgateway-system`) |
| `namespaces.zot` | Namespace where zot is installed (default: `zot-registry`) |

### Verify

```bash
kubectl get gateway zot-internal-gateway -n kgateway-system
NAME                   CLASS      ADDRESS       PROGRAMMED   AGE
zot-internal-gateway   kgateway   10.16.12.10   True         85m

kubectl get certificate -n kgateway-system
NAME                     READY   SECRET                     AGE
zot-internal-cert        True    zot-internal-cert-secret   85m
zot-public-cert-secret   True    zot-public-cert-secret     104m

kubectl get svc zot-internal-gateway -n kgateway-system
NAME                   TYPE           CLUSTER-IP   EXTERNAL-IP   PORT(S)          AGE
zot-internal-gateway   LoadBalancer   10.16.8.79   10.16.12.10   5000:31997/TCP   86m
```

---

## containerd DaemonSet (Node TLS Config)

Writes the internal CA cert and `hosts.toml` to every node so containerd can pull images from the internal registry over TLS without a restart. The CA cert is sourced directly from the secret named by `ca.secretName` — no manual cert distribution needed.

### Values (`zot-infra/values.yaml`)

| Key | Description |
|---|---|
| `internalGateway.lbIP` | Must match the internal Gateway LB IP |
| `ca.secretName` | Name of the secret holding the CA cert — mounted into the DaemonSet init container |
| `namespaces.certManager` | Namespace where the DaemonSet is created (default: `kube-system`) |

### Verify

```bash
kubectl -n kube-system get ds zot-internal-containerd-ds
NAME                         DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR   AGE
zot-internal-containerd-ds   1         1         1       1            1           <none>          81m

# Confirm files written on a node
cwic node shell WORKER_NODE_ID

ls /etc/containerd/certs.d/
10.16.12.10:5000

ls /etc/containerd/certs.d/10.16.12.10\:5000/
ca.crt  hosts.toml
```

### CA rotation

```bash
kubectl -n kube-system rollout restart ds/zot-internal-containerd-ds
```

---

## imagePullSecret

For workloads pulling from the internal registry, create an `imagePullSecret` in each namespace:

```bash
kubectl create secret docker-registry zot-pull-secret \
  --docker-server=<INTERNAL_LB_IP>:5000 \
  --docker-username=<ZOT_USERNAME> \
  --docker-password=<ZOT_PASSWORD> \
  -n <WORKLOAD_NAMESPACE>
```

Reference in pod specs:

```yaml
imagePullSecrets:
  - name: zot-pull-secret
```

---

## Example: Mirroring Images from ECR to Zot

Use a Kubernetes Job with `skopeo` to copy images from Amazon ECR into the Zot registry. The Job mounts the internal CA cert from the `<INTERNAL_CA_SECRET_NAME>` secret so skopeo can verify the Zot TLS endpoint.

ECR tokens expire every 12 hours. Retrieve a fresh token before running the Job:

```bash
export ECR_TOKEN=$(aws ecr get-login-password --region <AWS_REGION>)
```

```bash
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: skopeo-mirror-ecr
  namespace: kube-system
spec:
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: skopeo
          image: quay.io/skopeo/stable:latest
          command:
            - skopeo
            - copy
            - --multi-arch=all
            - --src-creds=AWS:${ECR_TOKEN}
            - --dest-creds=<ZOT_USERNAME>:<ZOT_PASSWORD>
            - --dest-cert-dir=/etc/zot-ca
            - --dest-tls-verify=true
            - docker://<AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/<ECR_IMAGE>:<TAG>
            - docker://<INTERNAL_LB_IP>:5000/<ECR_IMAGE>:<TAG>
          volumeMounts:
            - name: zot-ca
              mountPath: /etc/zot-ca
              readOnly: true
      volumes:
        - name: zot-ca
          secret:
            secretName: <INTERNAL_CA_SECRET_NAME>
            items:
              - key: ca.crt
                path: ca.crt
EOF
```

```bash
kubectl apply -f - <<'EOF'
apiVersion: batch/v1
kind: Job
metadata:
  name: skopeo-mirror-pytorch
  namespace: kube-system
spec:
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: skopeo
          image: quay.io/skopeo/stable:latest
          command:
            - skopeo
            - copy
            - --override-arch=amd64
            - --override-os=linux
            - --dest-creds=admin:$(ZOT_PASSWORD)
            - --dest-cert-dir=/ca
            - --dest-tls-verify=true
            - docker://docker.io/pytorch/pytorch:2.11.0-cuda12.8-cudnn9-devel
            - docker://10.16.12.10:5000/pytorch/pytorch:2.11.0-cuda12.8-cudnn9-devel
          env:
            - name: ZOT_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: zot-credentials
                  key: password
          volumeMounts:
            - name: ca-secret
              mountPath: /ca
              readOnly: true
      volumes:
        - name: ca-secret
          secret:
            secretName: zot-infra-ca-secret
            items:
              - key: ca.crt
                path: ca.crt
EOF
```

```bash
# Watch progress
kubectl logs -n kube-system -l job-name=skopeo-mirror-ecr -f

# Verify image landed in zot
curl -u <ZOT_USERNAME>:<ZOT_PASSWORD> \
  https://<INTERNAL_LB_IP>:5000/v2/<ECR_IMAGE>/tags/list \
  --cacert <(kubectl get secret <INTERNAL_CA_SECRET_NAME> -n kube-system \
    -o jsonpath='{.data.ca\.crt}' | base64 -d)
```

### Placeholders

| Placeholder | Description |
|---|---|
| `<AWS_REGION>` | AWS region of the ECR registry (e.g. `us-east-1`) |
| `<AWS_ACCOUNT_ID>` | AWS account ID |
| `<ECR_IMAGE>` | ECR repository and image name (e.g. `myorg/myapp`) |
| `<TAG>` | Image tag to mirror (e.g. `v1.0.0`) |
| `<ZOT_USERNAME>` / `<ZOT_PASSWORD>` | Zot registry credentials |
| `<INTERNAL_LB_IP>` | Internal MetalLB LB IP |
| `<INTERNAL_CA_SECRET_NAME>` | CA secret name (e.g. `internal-ca-secret`) |

---

## Benchmarks & Reports

Performance analysis and test artifacts are available under `zot-infra/reports/`:

| File | Description |
|---|---|
| [`zb-benchmark.md`](zot-infra/reports/zb-benchmark.md) | Analysis of zot registry throughput and latency with and without LOTA as the storage backend, covering push, pull, and mixed workloads across 1MB / 10MB / 100MB object sizes |
| [`enroot.md`](zot-infra/reports/enroot.md) | Analysis of `enroot import` performance against the zot registry with and without LOTA, including cold/warm cache behavior and the SLURM multi-user caching scenario |
| [`zb-bencharmarking.yaml`](zot-infra/reports/zb-bencharmarking.yaml) | Kubernetes Job manifest used to run the `zb` benchmark tool against the registry |
| [`zb-benchmark-with-lota.txt`](zot-infra/reports/zb-benchmark-with-lota.txt) | Raw `zb` output — zot backed by LOTA (`cwlota.com`) |
| [`zb-benchmark-without-lota.txt`](zot-infra/reports/zb-benchmark-without-lota.txt) | Raw `zb` output — zot backed by CAIOS directly (`cwobject.com`) |

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `x509: certificate signed by unknown authority` | CA cert not on node yet | Wait for DS pod to complete or check DS logs |
| `authorization failed: no basic auth credentials` | Pull secret server address mismatch | Recreate pull secret with exact registry address |
| `LoadBalancer Ingress` shows wrong IP | internal-lb cidr not honoring annotation | Verify IP is in an `IPAddressPool` range |
| `certificate not ready` | cert-manager cannot issue cert | Check `kubectl describe certificate` for events |
| Gateway `PROGRAMMED: False` | GatewayParameters or cert secret missing | Check `kubectl describe gateway` for conditions |
| `received unexpected HTTP status: 500` | skopeo using HTTP instead of HTTPS | Add `--dest-tls-verify=true` to skopeo command |
| `Invalid destination name docker://https://` | Incorrect skopeo destination format | Use `docker://IP:PORT` without `https://` prefix |
