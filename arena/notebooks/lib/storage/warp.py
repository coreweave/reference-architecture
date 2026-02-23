import os
import string
import uuid

from lib.k8s import K8s
from lib.storage.object_storage import ObjectStorage


def generate_warp_yaml(
    region: str,
    bucket_name: str,
    access_key: str,
    secret_key: str,
    host_count: int,
    compute_class: str = "gpu",
    endpoint: str = "cwlota.com",
) -> str:
    """Convert the warp yaml template into complete applicable yaml."""
    suffix = str(uuid.uuid4())[:8]
    return f"""
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: warp-config
  labels:
    app.kubernetes.io/name: warp
    app.kubernetes.io/instance: warp
data:
  warp-config.yml: |
    warp:
      advanced:
        debug: false
        disable-http-keepalive: false
        host-select: weighed
        http2: false
        rcvbuf: 32768
        resolve-host: false
        sndbuf: 32768
        stress: false
      analyze:
        verbose: false
      api: v1
      benchmark: get
      io:
        disable-multipart: false
        md5: false
        no-prefix: false
        prefix: benchmark-
        sse-s3-encrypt: false
        storage-class: STANDARD
      json: false
      no-color: false
      params:
        autoterm:
          dur: 10s
          enabled: false
          pct: 7.5
        concurrent: 300
        duration: 5m
        keep-data: false
        no-clear: false
        obj:
          rand-size: false
          size: 50MiB
        objects: 1000
      quiet: false
      remote:
        access-key: {access_key}
        bucket: {bucket_name}
        host:
        - {endpoint.lstrip("https://").lstrip("http://")}
        insecure: true
        lookup: host
        region: {region}
        secret-key: {secret_key}
      warp-client: warp-{{0...{host_count - 2}}}.warp
---
apiVersion: v1
kind: Service
metadata:
  name: warp
  labels:
    app.kubernetes.io/name: warp
    app.kubernetes.io/instance: warp
spec:
  publishNotReadyAddresses: true
  clusterIP: None
  selector:
    app.kubernetes.io/name: warp
    app.kubernetes.io/instance: warp
  ports:
    - port: 7761
      name: warp
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: warp
  labels:
    app.kubernetes.io/name: warp
    app.kubernetes.io/instance: warp
spec:
  serviceName: warp
  podManagementPolicy: Parallel
  replicas: {host_count - 1}
  selector:
    matchLabels:
      app.kubernetes.io/name: warp
      app.kubernetes.io/instance: warp
  template:
    metadata:
      name: warp
      labels:
        app.kubernetes.io/name: warp
        app.kubernetes.io/instance: warp
    spec:
      containers:
        - name: warp
          image: "minio/warp:v1.0.8"
          imagePullPolicy: IfNotPresent
          args:
            - client
          ports:
            - name: http
              containerPort: 7761
          securityContext:
            readOnlyRootFilesystem: true
      serviceAccountName: arena
      securityContext:
        fsGroup: 1001
        runAsNonRoot: true
        runAsUser: 1001
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: node.coreweave.cloud/state
                    operator: In
                    values:
                      - production
                  - key: node.coreweave.cloud/class
                    operator: In
                    values:
                      - {compute_class}
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchExpressions:
                  - key: app.kubernetes.io/instance
                    operator: In
                    values:
                      - warp
              topologyKey: kubernetes.io/hostname
      tolerations:
        - key: is_gpu
          operator: Exists
        - key: node.coreweave.cloud/reserved
          operator: Exists
---
apiVersion: batch/v1
kind: Job
metadata:
  name: warp-{suffix}
  labels:
    app.kubernetes.io/name: warp
    app.kubernetes.io/instance: warp
spec:
  template:
    metadata:
      annotations:
        # Force pod restart on upgrade by including a timestamp or revision
        rollme: "1"
    spec:
      restartPolicy: Never
      containers:
        - name: warp
          image: "minio/warp:v1.0.8"
          imagePullPolicy: IfNotPresent
          args:
            - run
            - /config/warp-config.yml
          securityContext:
            readOnlyRootFilesystem: true
          volumeMounts:
            - name: config
              mountPath: /config
              readOnly: true
      serviceAccountName: arena
      securityContext:
        fsGroup: 1001
        runAsNonRoot: true
        runAsUser: 1001
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: node.coreweave.cloud/state
                    operator: In
                    values:
                      - production
                  - key: node.coreweave.cloud/class
                    operator: In
                    values:
                      - gpu
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchExpressions:
                  - key: app.kubernetes.io/instance
                    operator: In
                    values:
                      - warp
              topologyKey: kubernetes.io/hostname
      tolerations:
        - key: is_gpu
          operator: Exists
        - key: node.coreweave.cloud/reserved
          operator: Exists
      volumes:
        - name: config
          configMap:
            name: warp-config
  backoffLimit: 4
"""


def run_warp_benchmark(k8s: K8s, object_storage: ObjectStorage, bucket_name: str) -> dict[str, list[str]]:
    """Run the warp benchmark on GPUs if possible, and CPUs if there aren't GPUs and return results of yaml application."""
    namespace = os.getenv("POD_NAMESPACE", "tenant-slurm")

    nodes = k8s.get_nodes()
    node_count = 0
    gpu_nodes = nodes.get("gpu", {})
    if not gpu_nodes:
        compute_class = "cpu"
        cpu_nodes = nodes.get("cpu", {})
        for cpu_node_type in cpu_nodes:
            node_count += cpu_nodes[cpu_node_type].get("node_count", 0)
    else:
        compute_class = "gpu"
        for gpu_node_type in gpu_nodes:
            node_count += gpu_nodes[gpu_node_type].get("node_count", 0)

    warp_yaml = generate_warp_yaml(
        region=object_storage.region,
        bucket_name=bucket_name,
        access_key=object_storage.access_key_id,
        secret_key=object_storage.secret_access_key,
        host_count=node_count,
        compute_class=compute_class,
        endpoint=object_storage.endpoint_url,
    )

    results = k8s.apply_yaml(warp_yaml, namespace)
    return results


def get_warp_benchmark_results(namespace: str):
    """Query, format, and return the results of the warp benchmark job."""
    pass
