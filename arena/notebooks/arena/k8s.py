import os
from typing import Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException


class KubernetesError(Exception):
    """
    Base exception for k8s helper errors
    """

    pass


class K8s:
    def __init__(self, in_cluster: bool = True, kubeconfig_path: Optional[str] = None):
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
        if self._core_v1 is None:
            self._core_v1 = client.CoreV1Api()
        return self._core_v1

    @property
    def apps_v1(self) -> client.AppsV1Api:
        if self._apps_v1 is None:
            self._apps_v1 = client.AppsV1Api()
        return self._apps_v1

    @property
    def batch_v1(self) -> client.BatchV1Api:
        if self._batch_v1 is None:
            self._batch_v1 = client.BatchV1Api()
        return self._batch_v1

    def get_pod_region(self, pod_name: Optional[str] = None, namespace: Optional[str] = None) -> Optional[str]:
        """
        Get region where pod is running, if pod_name and namespace are not provided, and running in a pod; detects them from the downward api.
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
