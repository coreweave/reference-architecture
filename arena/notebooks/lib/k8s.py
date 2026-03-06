import os
from typing import Callable

import marimo as mo
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
        core_v1 (client.CoreV1Api): Kubernetes Core API client for managing pods, services, etc.
        apps_v1 (client.AppsV1Api): Kubernetes Apps API client for managing deployments, statefulsets, etc.
        batch_v1 (client.BatchV1Api): Kubernetes Batch API client for managing jobs, cronjobs, etc.
        cluster_region (str): The CoreWeave region where the cluster is located (e.g., "ORD1").
        cluster_name (str): The name of the Kubernetes cluster.
        org_id (str): The CoreWeave organization ID.
        nodes (dict): Information about GPU and CPU nodes in the cluster.
        gpu_node_count (int): Total number of GPU nodes in the cluster.
        cpu_node_count (int): Total number of CPU nodes in the cluster.
        cw_token (str): Token detected from kube-config. Only works with local kubeconfig file.
    """

    def __init__(self, kubeconfig_path: str = "", context: str = ""):
        """Initialize Kubernetes client.

        Args:
            kubeconfig_path (str, optional): Path to kubeconfig file when in_cluster=False.
                Defaults to "" (uses default KUBECONFIG_PATH env var).
            context (str, optional): Kubernetes context to use when multiple available in the kubeconfig_path. If empty, uses current-context.

        Raises:
            KubernetesConfigError: If Kubernetes config cannot be loaded.
        """
        self._core_v1: client.CoreV1Api | None = None
        self._apps_v1: client.AppsV1Api | None = None
        self._batch_v1: client.BatchV1Api | None = None
        self._cluster_region: str | None = None
        self._cluster_name: str | None = None

        self.kubeconfig_path: str = kubeconfig_path or os.getenv("KUBECONFIG", "")
        self.context: str = context

        try:
            config.load_incluster_config()
            return
        except Exception:
            pass

        if self.kubeconfig_path:
            try:
                config.load_kube_config(config_file=self.kubeconfig_path, context=self.context or None)
                return
            except Exception as e:
                raise KubernetesConfigError(f"Failed to load Kubernetes config from {self.kubeconfig_path}: {e}")
        raise KubernetesConfigError(
            "Failed to load Kubernetes config. Not running in-cluster and no kubeconfig path provided or found in KUBECONFIG env var."
        )

    def validate_config(self) -> bool:
        """Check the kube config is valid and not expired.

        Only checks that:
            - API server is reachable
            - The client has permissions to get cluster k8s version
        Returns: bool
        """
        try:
            client.VersionApi().get_code()
            return True
        except Exception as e:
            return False

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
        if os.getenv("CLUSTER_REGION") is not None:
            self._cluster_region = os.getenv("CLUSTER_REGION", "")
            return self._cluster_region
        try:
            nodes = self.core_v1.list_node()
            if not nodes.items:
                raise KubernetesError("No nodes found in cluster")

            first_node = nodes.items[0]
            if first_node.metadata is None or first_node.metadata.labels is None:
                raise KubernetesError("First node metadata or labels are missing")

            region = first_node.metadata.labels.get("topology.kubernetes.io/region") or first_node.metadata.labels.get(
                "failure-domain.beta.kubernetes.io/region"
            )

            if region:
                region = region + AVAILABILITY_ZONE
            else:
                raise KubernetesError("Unable to detect region, manually set with env var CLUSTER_REGION")

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

    @property
    def nodes(self) -> dict[str, dict[str, dict]]:
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
            if nodes.items:
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

    @property
    def gpu_node_count(self) -> int:
        """Get the total number of GPU nodes in the cluster."""
        nodes = self.nodes
        return sum(info["node_count"] for info in nodes["gpu"].values())

    @property
    def cpu_node_count(self) -> int:
        """Get the total number of CPU nodes in the cluster."""
        nodes = self.nodes
        return sum(info["node_count"] for info in nodes["cpu"].values())

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
        self,
        name: str,
        namespace: str,
        doc: dict,
        kind: str,
        results: dict,
        read_fn: Callable,
        create_fn: Callable,
        patch_fn: Callable,
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

    @property
    def cluster_name(self) -> str:
        """Get the cluster name for the current k8s client.

        Attempts to get the cluster name from:
            1. Node label 'node.coreweave.cloud/cluster on the first node
            2. Current context name in kubeconfig

        Raises:
            KubernetesError: If cluster name cannot be determined
        """
        if self._cluster_name is not None:
            return self._cluster_name

        try:
            nodes: V1NodeList = self.core_v1.list_node()
            if not nodes.items:
                raise KubernetesError("No nodes found in cluster")

            first_node = nodes.items[0]
            if first_node.metadata is None or first_node.metadata.labels is None:
                raise KubernetesError("First node metadata or labels are missing")

            cluster_name = first_node.metadata.labels.get(
                "cks.coreweave.com/cluster"
            ) or first_node.metadata.labels.get("node.coreweave.cloud/cluster")

            if not cluster_name:
                # Try to get cluster name from kubeconfig context
                # Fails if running in-cluster
                try:
                    contexts, active_context = config.list_kube_config_contexts()
                    if active_context and active_context.get("name"):
                        cluster_name = active_context["name"]
                except config.ConfigException:
                    # Running in-cluster without kubeconfig, can only rely on node labels
                    pass

            if not cluster_name:
                raise KubernetesError("Cluster name not found in node labels or kubeconfig context")

            self._cluster_name = cluster_name
            return cluster_name

        except ApiException as e:
            raise KubernetesError(f"Failed to get cluster name: {e}")

    def delete_by_label(self, namespace: str, label_selector: str) -> dict[str, list[str]]:
        """Delete all resources in a namespace matching a label selector.

        Args:
            namespace: Kubernetes namespace to delete resources from
            label_selector: Label selector (e.g., "app.kubernetes.io/name=warp")

        Returns:
            dict: Results of deletion operations with categorized resource names:
                {
                    "deleted": ["Job/warp-abc123", "StatefulSet/warp"],
                    "not_found": [],
                    "failed": ["Service/warp: Forbidden"]
                }
        """
        results: dict[str, list[str]] = {
            "deleted": [],
            "not_found": [],
            "failed": [],
        }

        resource_types = [
            ("Job", self.batch_v1.list_namespaced_job, self.batch_v1.delete_namespaced_job),
            ("StatefulSet", self.apps_v1.list_namespaced_stateful_set, self.apps_v1.delete_namespaced_stateful_set),
            ("Deployment", self.apps_v1.list_namespaced_deployment, self.apps_v1.delete_namespaced_deployment),
            ("Service", self.core_v1.list_namespaced_service, self.core_v1.delete_namespaced_service),
            ("ConfigMap", self.core_v1.list_namespaced_config_map, self.core_v1.delete_namespaced_config_map),
            ("Secret", self.core_v1.list_namespaced_secret, self.core_v1.delete_namespaced_secret),
            (
                "PersistentVolumeClaim",
                self.core_v1.list_namespaced_persistent_volume_claim,
                self.core_v1.delete_namespaced_persistent_volume_claim,
            ),
            ("Pod", self.core_v1.list_namespaced_pod, self.core_v1.delete_namespaced_pod),
        ]

        for kind, list_func, delete_func in resource_types:
            try:
                resources = list_func(namespace=namespace, label_selector=label_selector)

                for item in resources.items:
                    name = item.metadata.name
                    resource_name = f"{kind}/{name}"

                    try:
                        if kind in ["Job", "StatefulSet", "Deployment"]:
                            delete_func(
                                name=name,
                                namespace=namespace,
                                propagation_policy="Foreground",
                            )
                        else:
                            delete_func(name=name, namespace=namespace)

                        results["deleted"].append(resource_name)
                    except ApiException as e:
                        if e.status == 404:
                            results["not_found"].append(resource_name)
                        else:
                            results["failed"].append(f"{resource_name}: {e}")
                    except Exception as e:
                        results["failed"].append(f"{resource_name}: {e}")

                # If we can't list this resource type, skip
            except Exception as e:
                results["failed"].append(f"Failed to list {kind}: {e}")

        return results


def kubeconfig_input() -> tuple[mo.Html | None, mo.ui.form | None]:
    """Create a form for a user to input their kubeconfig path.

    To access the path in your code, use kubeconfig_form.value.get("kubeconfig_path")
    """
    kubeconfig_form = (
        mo.md("{kubeconfig_path}")
        .batch(kubeconfig_path=mo.ui.text(placeholder="~/.kube/config", full_width=True))  # type: ignore
        .form(submit_button_label="Connect", bordered=False)
    )
    kubeconfig_ui = mo.md(
        f"""
        /// admonition | Manual Initialization Required
            type: warning

        Automatic Kubernetes credentials not found or invalid. Please enter the path to your [CoreWeave Kubeconfig](https://console.coreweave.com/tokens) to initialize the Kubernetes client for submitting Warp jobs.
        ///

        {kubeconfig_form}
        """
    )
    return kubeconfig_ui, kubeconfig_form
