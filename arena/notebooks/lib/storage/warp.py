import os
import uuid
from typing import Optional

from lib.k8s import K8s
from lib.storage.object_storage import ObjectStorage


class WarpRunner:
    """Runner for Warp S3 CoreWeave benchmarks on Kubernetes.

    Manages the lifecycle of the warp benchmark jobs and clients including deployment, monitoring
    and result collection and parsing
    """

    def __init__(self, k8s: K8s, bucket_name: str, object_storage: ObjectStorage, namespace: Optional[str] = None):
        """Initialize WarpRunner.

        Args:
            k8s: Kubernetes client instance
            bucket_name: Name of CoreWeave bucket to run tests again
            object_storage: ObjectStorage client with credentials
            namespace: Kubernetes namespace for warp resources (defaults to POD_NAMESPACE env var)
        """
        self.k8s = k8s
        self.object_storage = object_storage
        self.namespace = namespace or os.getenv("POD_NAMESPACE", "tenant-slurm")
        self.bucket_name = bucket_name
        self.job_name: Optional[str] = None
        self.job_suffix: Optional[str] = None

    def run_benchmark(
        self, benchmark_type: str = "get", duration: str = "10m", compute_class: Optional[str] = None
    ) -> dict[str, list[str]]:
        """Run the warp benchmark on GPUs if possible, and CPUs if there aren't GPUs and return results of yaml application.

        Returns:
            dict: Results of applying the warp benchmark yaml to the cluster
                {
                "created": [
                    "Job/warp-00206435"
                ],
                "updated": [
                    "ConfigMap/warp-config",
                    "Service/warp",
                    "StatefulSet/warp"
                ],
                "unchanged": []
                }
        """
        nodes = self.k8s.get_nodes()
        node_count = 0

        if compute_class is None:
            gpu_nodes = nodes.get("gpu", {})
            if gpu_nodes:
                compute_class = "gpu"
                for gpu_node_type in gpu_nodes:
                    node_count += gpu_nodes[gpu_node_type].get("node_count", 0)
            else:
                compute_class = "cpu"
                cpu_nodes = nodes.get("cpu", {})
                for cpu_node_type in cpu_nodes:
                    node_count += cpu_nodes[cpu_node_type].get("node_count", 0)

        warp_yaml = self._generate_warp_yaml(
            host_count=node_count,
            compute_class=compute_class,
            benchmark_type=benchmark_type,
            duration=duration,
        )

        results = self.k8s.apply_yaml(warp_yaml, self.namespace)
        # this is a bit sloppy since it assumes only one job is created, but that is currently the case so :shrug:
        for resource in results.get("created", []):
            if resource.startswith("Job/"):
                self.job_name = resource.split("/")[1]
                break

        return results

    def get_results(self) -> dict:
        """Get current benchmark results.

        Returns:
            dict: Parsed benchmark results with metrics
                {
                    "status": "succeeded",
                    "pod_name" "warp-job-rsent37",
                    "logs": [str]
                }
        """
        if not self.job_name:
            return {"status": "error", "error": "No job running"}
        pods = self.k8s.core_v1.list_namespaced_pod(
            namespace=self.namespace, label_selector=f"job-name={self.job_name}"
        )

        if not pods.items:
            return {"status": "no_pods_found", "error": "Job pods not found"}

        pod_name = pods.items[0].metadata.name
        pod_status = pods.items[0].status.phase

        if pod_status not in ["Succeeded", "Running", "Failed"]:
            return {"status": pod_status.lower(), "pod_name": pod_name, "message": f"Pod is in {pod_status} state"}

        try:
            logs: str = self.k8s.core_v1.read_namespaced_pod_log(
                name=pod_name, namespace=self.namespace, container="warp"
            )
            return {"status": pod_status.lower(), "logs": logs}
        except Exception as e:
            return {"status": "error", "error": f"Failed to fetch logs: {str(e)}", "pod_name": pod_name}

    def _parse_logs(self, logs: str) -> dict:
        """Parse warp benchmark output logs to get only the results."""
        pass

    def _generate_warp_yaml(
        self, host_count: int, compute_class: str = "gpu", benchmark_type: str = "get", duration: str = "10m"
    ) -> str:
        """Convert the warp yaml template into complete applicable yaml."""
        self.job_suffix = str(uuid.uuid4())[:8]
        endpoint = self.object_storage.endpoint_url.lstrip("https://").strip("http://")
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
      benchmark: {benchmark_type}
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
        duration: {duration}
        keep-data: false
        no-clear: false
        obj:
          rand-size: false
          size: 50MiB
        objects: 1000
      quiet: false
      remote:
        access-key: {self.object_storage.access_key_id}
        bucket: {self.bucket_name}
        host:
        - {endpoint}
        insecure: true
        lookup: host
        region: {self.object_storage.region}
        secret-key: {self.object_storage.secret_access_key}
      warp-client: warp-{{0...{host_count - 2}}}.warp.{self.namespace}.svc.cluster.local
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
  name: warp-{self.job_suffix}
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
      initContainers:
          - name: wait-for-clients
            image: busybox:1.37
            command:
                - sh
                - -c
                - |
                    echo "Waiting for warp clients to be ready..."
                    for i in $(seq 0 {host_count - 2}); do
                    until nslookup warp-$i.warp.{self.namespace}.svc.cluster.local; do
                        echo "Waiting for warp-$i.warp..."
                        sleep 2
                    done
                    echo "warp-$i is ready"
                    done
                    echo "All warp clients are ready!"
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
