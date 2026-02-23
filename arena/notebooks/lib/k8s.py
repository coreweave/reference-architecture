import os
from typing import Any, Optional

from kubernetes import client, config
from kubernetes.client.models.v1_node_list import V1NodeList
from kubernetes.client.rest import ApiException


class KubernetesError(Exception):
    """Base exception for k8s helper errors."""

    pass


class K8s:
    """Helper class for interacting with Kubernetes clusters.

    Provides lazy-loaded access to Kubernetes API clients (Core, Apps, Batch).
    Handles both in-cluster and local kubeconfig authentication.

    Attributes:
        _core_v1 (client.CoreV1Api | None): Cached CoreV1Api client.
        _apps_v1 (client.AppsV1Api | None): Cached AppsV1Api client.
        _batch_v1 (client.BatchV1Api | None): Cached BatchV1Api client.
    """

    def __init__(self, in_cluster: bool = True, kubeconfig_path: Optional[str] = None):
        """Initialize Kubernetes client.

        Args:
            in_cluster (bool, optional): If True, load in-cluster config (for pods). If False,
                load from kubeconfig file. Defaults to True.
            kubeconfig_path (str, optional): Path to kubeconfig file when in_cluster=False.
                Defaults to None (uses default kubeconfig locations).

        Raises:
            KubernetesError: If Kubernetes config cannot be loaded.
        """
        self._core_v1: client.CoreV1Api | None = None
        self._apps_v1: client.AppsV1Api | None = None
        self._batch_v1: client.BatchV1Api | None = None

        try:
            if in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config(config_file=kubeconfig_path)
        except Exception as e:
            raise KubernetesError(f"Failed to load Kubernetes config: {e}")

    @property
    def core_v1(self) -> client.CoreV1Api:
        """Get the CoreV1Api client.

        Lazily initializes the client on first access and caches it for subsequent calls.

        Returns:
            client.CoreV1Api: Kubernetes Core API client for managing pods, services, etc.
        """
        if self._core_v1 is None:
            self._core_v1 = client.CoreV1Api()
        return self._core_v1

    @property
    def apps_v1(self) -> client.AppsV1Api:
        """Get the AppsV1Api client.

        Lazily initializes the client on first access and caches it for subsequent calls.

        Returns:
            client.AppsV1Api: Kubernetes Apps API client for managing deployments, statefulsets, etc.
        """
        if self._apps_v1 is None:
            self._apps_v1 = client.AppsV1Api()
        return self._apps_v1

    @property
    def batch_v1(self) -> client.BatchV1Api:
        """Get the BatchV1Api client.

        Lazily initializes the client on first access and caches it for subsequent calls.

        Returns:
            client.BatchV1Api: Kubernetes Batch API client for managing jobs, cronjobs, etc.
        """
        if self._batch_v1 is None:
            self._batch_v1 = client.BatchV1Api()
        return self._batch_v1

    def get_pod_region(self, pod_name: Optional[str] = None, namespace: Optional[str] = None) -> Optional[str]:
        """Get the CW region where a pod is running.

        Reads the pod's node and retrieves the region from node labels. If pod_name and
        namespace are not provided, attempts to read them from POD_NAME and POD_NAMESPACE
        environment variables (set by Kubernetes downward API).

        Args:
            pod_name (str, optional): Name of the pod. Defaults to None (reads from POD_NAME env var).
            namespace (str, optional): Namespace containing the pod. Defaults to None
                (reads from POD_NAMESPACE env var).

        Returns:
            str | None: CW region label from the node (e.g., "us-east-04"), or None if not found.

        Raises:
            KubernetesError: If pod_name and namespace cannot be determined, or if the Kubernetes
                API call fails.

        Note:
            When running in a pod, POD_NAME and POD_NAMESPACE should be set via the downward API:
            env:
              - name: POD_NAME
                valueFrom:
                  fieldRef:
                    fieldPath: metadata.name
              - name: POD_NAMESPACE
                valueFrom:
                  fieldRef:
                    fieldPath: metadata.namespace
        """
        try:
            pod_name = pod_name or os.getenv("POD_NAME")
            namespace = namespace or os.getenv("POD_NAMESPACE")

            if not pod_name or not namespace:
                raise KubernetesError(
                    "pod_name and namespace must be provided or set via POD_NAME and POD_NAMESPACE environment variable"
                )

            pod = self.core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            if pod.spec is None or pod.spec.node_name is None:
                return None

            node = self.core_v1.read_node(name=pod.spec.node_name)
            if node.metadata is None or node.metadata.labels is None:
                return None

            return node.metadata.labels.get("topology.kubernetes.io/region") or node.metadata.labels.get(
                "failure-domain.beta.kubernetes.io/region"
            )

        except ApiException as e:
            raise KubernetesError(f"Failed to get pod region: {e}")

    def get_cluster_region(self) -> Optional[str]:
        """Get the region of the Kubernetes cluster.

        Reads the region from the first node's labels.

        Returns:
            str | None: CW region label from the node (e.g., "us-east-04"), or None if no nodes are found.

        Raises:
            KubernetesError: If the Kubernetes API call fails or if node metadata/labels are missing.
        """
        try:
            nodes = self.core_v1.list_node()
            if not nodes.items:
                return None

            first_node = nodes.items[0]
            if first_node.metadata is None or first_node.metadata.labels is None:
                raise KubernetesError("First node metadata or labels are missing")

            return first_node.metadata.labels.get("topology.kubernetes.io/region") or first_node.metadata.labels.get(
                "failure-domain.beta.kubernetes.io/region"
            )

        except ApiException as e:
            raise KubernetesError(f"Failed to get cluster region: {e}")

    def get_nodes(self) -> dict[str, dict[Any, Any]]:
        """Get the number and type of nodes in the cluster.

        Counts nodes with nvidia.com/gpu resources as gpu nodes and
        nodes without as cpu nodes. Groups by node type label and tracks
        GPU count per node.

        Returns:
            dict: Dictionary with 'gpu' and 'cpu' keys, each containing
                  a dict mapping node types to their counts and GPU info.
                  Example: {
                      'gpu': {
                          'gd-8xh100ib-i128': {'node_count': 4, 'gpus_per_node': 8, 'total_gpus': 32},
                      },
                      'cpu': {
                          'cd-gp-i64-erapids': {'node_count': 2, 'cpu_cores_per_node': 64, 'total_cpus': 128}
                      }
                  }

        Raises:
            KubernetesError: If the API call fails.
        """
        try:
            nodes: V1NodeList = self.core_v1.list_node()

            gpu_nodes: dict[str, dict[str, int]] = {}
            cpu_nodes: dict[str, dict[str, int]] = {}
            for node in nodes.items:
                if int(node.status.capacity.get("nvidia.com/gpu", 0)) > 0:
                    gpu_per_node = int(node.status.capacity.get("nvidia.com/gpu", 0))
                    cpu_cores_per_node = int(node.status.capacity.get("cpu", 0))
                    gpu_type = node.metadata.labels.get("node.coreweave.cloud/type", "unknown")

                    if gpu_type not in gpu_nodes:
                        gpu_nodes[gpu_type] = {
                            "node_count": 0,
                            "gpus_per_node": int(gpu_per_node),
                            "total_gpus": 0,
                            "cpu_cores_per_node": cpu_cores_per_node,
                        }
                    gpu_nodes[gpu_type]["node_count"] += 1
                    gpu_nodes[gpu_type]["total_gpus"] += gpu_per_node

                else:
                    cpu_cores_per_node = int(node.status.capacity.get("cpu", 0))
                    cpu_type = node.metadata.labels.get("node.coreweave.cloud/type", "unknown")

                    if cpu_type not in cpu_nodes:
                        cpu_nodes[cpu_type] = {
                            "node_count": 0,
                            "cpu_cores_per_node": cpu_cores_per_node,
                            "total_cpus": 0,
                        }
                    cpu_nodes[cpu_type]["node_count"] += 1
                    cpu_nodes[cpu_type]["total_cpus"] += cpu_cores_per_node

            return {"gpu": gpu_nodes, "cpu": cpu_nodes}
        except ApiException as e:
            raise KubernetesError(f"Failed to get node details: {e}")
