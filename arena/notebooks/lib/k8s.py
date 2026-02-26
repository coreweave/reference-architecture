import os
from typing import Optional

from kubernetes import client, config
from kubernetes.client.models.v1_node_list import V1NodeList
from kubernetes.client.rest import ApiException
from ruamel.yaml import YAML

# We don't have a good way to get this off node labels currently
AVAILABILITY_ZONE = os.getenv("AVAILABILITY_ZONE", "A")


class KubernetesError(Exception):
    """Base exception for k8s helper errors."""

    pass


class KubernetesConfigError(KubernetesError):
    """Raised when Kubernetes config cannot be loaded in-cluster or from path."""

    pass


class K8s:
    """Helper class for interacting with Kubernetes clusters.

    Provides lazy-loaded access to Kubernetes API clients (Core, Apps, Batch).
    Handles both in-cluster and local kubeconfig authentication.

    Attributes:
        _core_v1 (client.CoreV1Api | None): Cached CoreV1Api client.
        _apps_v1 (client.AppsV1Api | None): Cached AppsV1Api client.
        _batch_v1 (client.BatchV1Api | None): Cached BatchV1Api client.
        _cluster_region (str | None): Cached cluster region value
    """

    def __init__(self, kubeconfig_path: str = "~/.kube/config"):
        """Initialize Kubernetes client.

        Args:
            in_cluster (bool, optional): If True, load in-cluster config (for pods). If False,
                load from kubeconfig file. Defaults to True.
            kubeconfig_path (str, optional): Path to kubeconfig file when in_cluster=False.
                Defaults to None (uses default kubeconfig locations).

        Raises:
            KubernetesConfigError: If Kubernetes config cannot be loaded.
        """
        self._core_v1: client.CoreV1Api | None = None
        self._apps_v1: client.AppsV1Api | None = None
        self._batch_v1: client.BatchV1Api | None = None
        self._cluster_region: str | None = None

        try:
            config.load_incluster_config()
            print("Loaded in-cluster Kubernetes config")
        except Exception:
            try:
                print(f"Loading kubeconfig from {kubeconfig_path}, set env var KUBECONFIG_PATH to override")
                config.load_kube_config(config_file=kubeconfig_path)
            except Exception as e:
                raise KubernetesConfigError(
                    f"Failed to load Kubernetes config in-cluster or from path {kubeconfig_path}, set env var KUBECONFIG_PATH to override: {e}"
                )

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

    def pod_region(self, pod_name: Optional[str] = None, namespace: Optional[str] = None) -> str:
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
                raise KubernetesError("Unable to get pod spec or name")

            node = self.core_v1.read_node(name=pod.spec.node_name)
            if node.metadata is None or node.metadata.labels is None:
                raise KubernetesError("Unable to get node metadata")

            region = node.metadata.labels.get("topology.kubernetes.io/region") or node.metadata.labels.get(
                "failure-domain.beta.kubernetes.io/region"
            )
            region = region + AVAILABILITY_ZONE

            return region

        except ApiException as e:
            raise KubernetesError(f"Failed to get pod region: {e}")

    @property
    def cluster_region(self) -> str:
        """Get the region of the Kubernetes cluster.

        Reads the region from the first node's labels.

        Returns:
            str | None: CW region label from the node (e.g., "us-east-04"), or None if no nodes are found.

        Raises:
            KubernetesError: If the Kubernetes API call fails or if node metadata/labels are missing.
        """
        if self._cluster_region is not None:
            return self._cluster_region
        try:
            nodes = self.core_v1.list_node()
            if not nodes.items:
                raise KubernetesError("No nodes found in cluster")

            first_node = nodes.items[0]
            if first_node.metadata is None or first_node.metadata.labels is None:
                raise KubernetesError("First node metadata or labels are missing")

            region = (
                first_node.metadata.labels.get("topology.kubernetes.io/region")
                or first_node.metadata.labels.get("failure-domain.beta.kubernetes.io/region")
                or ""
            )

            region = region + AVAILABILITY_ZONE

            self._cluster_region = region

            return region

        except ApiException as e:
            raise KubernetesError(f"Failed to get cluster region: {e}")

    @cluster_region.setter
    def cluster_region(self, region: str):
        """Set the cluster region manually, overriding autodetection.

        Args:
            region (str): The region to set "US-WEST-04A"
        """
        self._cluster_region = region

    def get_nodes(self) -> dict[str, dict[str, dict]]:
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

    def _create_or_update_resource(self, kind: str, name: str, namespace: str, doc: dict, results: dict) -> None:
        """Helper method to create or update a Kubernetes resource.

        Args:
            kind: Resource kind (e.g., 'ServiceAccount', 'ConfigMap')
            name: Resource name
            namespace: Target namespace
            doc: Resource definition dictionary
            results: Results dictionary to append to

        Raises:
            ApiException: If resource operation fails
        """
        match kind:
            case "ServiceAccount":
                self._apply_resource(
                    name,
                    namespace,
                    doc,
                    kind,
                    results,
                    self.core_v1.read_namespaced_service_account,
                    self.core_v1.create_namespaced_service_account,
                    self.core_v1.patch_namespaced_service_account,
                )

            case "ConfigMap":
                self._apply_resource(
                    name,
                    namespace,
                    doc,
                    kind,
                    results,
                    self.core_v1.read_namespaced_config_map,
                    self.core_v1.create_namespaced_config_map,
                    self.core_v1.patch_namespaced_config_map,
                )

            case "Service":
                self._apply_resource(
                    name,
                    namespace,
                    doc,
                    kind,
                    results,
                    self.core_v1.read_namespaced_service,
                    self.core_v1.create_namespaced_service,
                    self.core_v1.patch_namespaced_service,
                )

            case "StatefulSet":
                self._apply_resource(
                    name,
                    namespace,
                    doc,
                    kind,
                    results,
                    self.apps_v1.read_namespaced_stateful_set,
                    self.apps_v1.create_namespaced_stateful_set,
                    self.apps_v1.patch_namespaced_stateful_set,
                )

            case "Job":
                # Jobs cannot be updated
                try:
                    self.batch_v1.read_namespaced_job(name, namespace)
                    results["unchanged"].append(f"{kind}/{name} (jobs cannot be updated)")
                except ApiException as e:
                    if e.status == 404:
                        self.batch_v1.create_namespaced_job(namespace, doc)
                        results["created"].append(f"{kind}/{name}")
                    else:
                        raise

            case _:
                results["unchanged"].append(f"{kind}/{name} (unsupported resource type)")

    def _apply_resource(
        self, name: str, namespace: str, doc: dict, kind: str, results: dict, read_fn, create_fn, patch_fn
    ) -> None:
        """Apply a resource by attempting to read, then update or create.

        Supports serviceaccount, configmap, service, statefulset, and job

        Args:
            name: Resource name
            namespace: Target namespace
            doc: Resource definition dictionary
            kind: Resource kind
            results: Results dictionary to append to
            read_fn: Function to read the resource
            create_fn: Function to create the resource
            patch_fn: Function to patch the resource
        """
        try:
            read_fn(name, namespace)
            patch_fn(name, namespace, doc)
            results["updated"].append(f"{kind}/{name}")
        except ApiException as e:
            if e.status == 404:
                create_fn(namespace, doc)
                results["created"].append(f"{kind}/{name}")
            else:
                raise

    def apply_yaml(self, yaml_content: str, namespace: str) -> dict[str, list[str]]:
        """Apply YAML resources, creating or updating as needed.

        Uses ruamel.yaml to preserve formatting and handle YAML parsing correctly.

        Args:
            yaml_content: YAML string with Kubernetes resources
            namespace: Target namespace

        Returns:
            dict: Results of apply operations with keys 'created', 'updated', 'unchanged'

        Raises:
            KubernetesError: If parsing or applying YAML fails
        """
        results: dict[str, list[str]] = {"created": [], "updated": [], "unchanged": []}

        try:
            yaml = YAML(typ="safe")
            documents = list(yaml.load_all(yaml_content))

            for doc in documents:
                if not doc:
                    continue

                kind = doc.get("kind")
                name = doc.get("metadata", {}).get("name")

                if not kind or not name:
                    continue

                try:
                    self._create_or_update_resource(kind, name, namespace, doc, results)
                except ApiException as e:
                    raise KubernetesError(f"Failed to apply {kind}/{name}: {e}")

            return results

        except Exception as e:
            raise KubernetesError(f"Failed to parse or apply YAML: {e}")

    @property
    def org_id(self) -> str:
        """Detect the CoreWeave org ID by checking the first node's cks.coreweave.com/org-id label. cks.coreweave.com/org-id=cw623e."""
        try:
            nodes = self.core_v1.list_node()
            if not nodes.items:
                raise KubernetesError("No nodes found")

            first_node = nodes.items[0]
            if first_node.metadata is None or first_node.metadata.labels is None:
                raise KubernetesError("First node metadata or labels are missing")

            return first_node.metadata.labels.get("cks.coreweave.com/org-id")
        except Exception as e:
            raise KubernetesError(f"Failed to get org ID from node labels: {e}")
