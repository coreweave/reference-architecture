import json
import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, Optional

import boto3
import requests
from botocore.config import Config

from ..k8s import K8s

COREWEAVE_OBJECT_API_BASE_URL = "https://api.coreweave.com/v1/cwobject"
LOTA_ENDPOINT_URL = "http://cwlota.com"
CAIOS_ENDPOINT_URL = "https://cwobject.com"
DEFAULT_ACCESS_TOKEN_DURATION = 43200  # 12h
DEFAULT_ADDRESSING_STYLE = "virtual"

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
else:
    S3Client = object


class ObjectStorageError(Exception):
    """Base exception for ObjectStorage errors."""

    pass


class MissingCredentialsError(ObjectStorageError):
    """Raised when required credentials are missing."""

    pass


class MissingRegionError(ObjectStorageError):
    """Raised when unable to get a region."""

    pass


class ObjectStorage(ABC):
    """Abstract base class for CAIOS operations.

    Provides s3 access and cw api org policy management.
    It passes through commonly used s3_client functions.

    Attributes:
        use_lota (bool): Whether to use LOTA endpoint (GPU clusters) vs CAIOS endpoint.
        region (str): CW region for bucket operations.
        addressing_style (Literal["path","virtual","auto"]): S3 addressing style.
        cw_token (str): CW api token for authentication.
        s3_config (Config): S3 configuration for botocore
        endpoint_url (str): The fully formed url to perform s3 operations against
    """

    def __init__(
        self,
        k8s: K8s,
        cw_token: str = "",
        use_lota: bool = True,
        region: str = "",
        availability_zone: str = "A",
    ):
        """Initialize ObjectStorage base class.

        Args:
            k8s (K8s): Kubernetes client for interacting with the cluster
            cw_token (str, optional): CoreWeave API token. Defaults to CW_TOKEN env var.
            use_lota (bool, optional): Use LOTA endpoint for GPU clusters. Defaults to True.
            region (str, optional): CW region. Defaults to auto-detected region.
            availability_zone (str, optional): CW availability zone, needed since we can't detect it from in-cluster. Defaults to 'A'.
        """
        self.use_lota = use_lota
        self._s3_client: S3Client | None = None
        self._api_session: requests.Session | None = None
        self.k8s = k8s
        self.region = region if region else f"{detect_region(self.k8s)}{availability_zone}"

        style = os.environ.get("AWS_S3_ADDRESSING_STYLE")
        self.addressing_style: Literal["path", "virtual", "auto"] = (
            style if style in ("path", "virtual", "auto") else DEFAULT_ADDRESSING_STYLE
        )

        self.cw_token = cw_token if cw_token else os.environ.get("CW_TOKEN", "")

        # shared s3_config for all auth methods
        self.s3_config = Config(
            s3={"addressing_style": self.addressing_style},
            connect_timeout=5,
            read_timeout=10,
            retries={"max_attempts": 2},
        )

        self.endpoint_url = LOTA_ENDPOINT_URL if self.use_lota else CAIOS_ENDPOINT_URL

        self._access_key_id: Optional[str] = None
        self._secret_access_key: Optional[str] = None
        self._credentials_expiry: Optional[datetime] = None
        self._credential_duration: int = DEFAULT_ACCESS_TOKEN_DURATION

    @property
    def access_key_id(self) -> str:
        """Get access key ID, refreshing if necessary."""
        if self._should_refresh_credentials():
            self._refresh_credentials()
        return self._access_key_id or ""

    @property
    def secret_access_key(self) -> str:
        """Get secret access key, refreshing if necessary."""
        if self._should_refresh_credentials():
            self._refresh_credentials()
        return self._secret_access_key or ""

    def _should_refresh_credentials(self) -> bool:
        """Check if credentials need to be refreshed.

        Returns:
            bool: True if credentials should be refreshed.
        """
        if not self._access_key_id or not self._secret_access_key:
            return True
        if self._credentials_expiry is None:
            return False
        # Refresh 5 minutes before expiry
        return datetime.now(UTC) >= (self._credentials_expiry - timedelta(minutes=5))

    def _refresh_credentials(self) -> None:
        """Refresh temporary credentials."""
        if not self.cw_token:
            raise ObjectStorageError("Cannot refresh credentials without CW token")

        access_key_id, secret_access_key = self._fetch_temp_access_keys(self._credential_duration)
        self._set_credentials(access_key_id, secret_access_key, self._credential_duration)

    @abstractmethod
    def _fetch_temp_access_keys(self, duration_seconds: int = DEFAULT_ACCESS_TOKEN_DURATION) -> tuple[str, str]:
        """Generate temporary S3 access keys via CoreWeave API."""
        pass

    def _set_credentials(self, access_key_id: str, secret_access_key: str, duration_seconds: int) -> None:
        """Set credentials and track expiry time.

        Args:
            access_key_id: AWS access key ID
            secret_access_key: AWS secret access key
            duration_seconds: How long the credentials are valid for
        """
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._credentials_expiry = datetime.now(UTC) + timedelta(seconds=duration_seconds)
        self._credential_duration = duration_seconds
        # Invalidate cached S3 client so it gets recreated with new credentials
        self._s3_client = None

    @staticmethod
    def auto(k8s: K8s, cw_token: str = "", use_lota: bool = True, region: str = "") -> "ObjectStorage":
        """Auto detect and create the ObjectStorage client.

        Attempts authentication methods in order:
        1. Pod Identity with LOTA (falls back to CAIOS on connection errors)
        2. Access Keys with LOTA (falls back to CAIOS on connection errors)

        Args:
            k8s (K8s): Kubernetes client for interacting with the cluster
            cw_token (str, optional): CoreWeave API token.
            use_lota (bool, optional): Prefer LOTA endpoint. Defaults to True.
            region (str, optional): CoreWeave region.

        Returns:
            ObjectStorage: Authenticated client instance (PodIdentityObjectStorage or AccessKeyObjectStorage).

        Raises:
            ObjectStorageError: If all authentication methods fail.
        """
        print("Initializing CoreWeave AI object storage")
        # Choose our subclass with preference for PodIdentity if it works
        try:
            print(f"Attempting pod identity authentication with {'LOTA' if use_lota else 'CAIOS'}...")
            client = PodIdentityObjectStorage(k8s, cw_token, use_lota, region)
            print("Testing pod identity credentials...")
            client.s3_client.list_buckets()
            print(f"Initialized CAIOS client using pod identity authentication ({'LOTA' if use_lota else 'CAIOS'}).")
            return client
        except Exception as e:
            # fallback to cwobject if lota isn't reachable from our location (local or non-gpu cluster)
            e_msg = str(e).lower()
            if use_lota and ("timeout" in e_msg or "connect" in e_msg):
                print(f"LOTA endpoint failed ({e})\n  Does your cluster have GPUs? Trying CWObject endpoint...")
                try:
                    client = PodIdentityObjectStorage(k8s, cw_token, use_lota=False, region=region)
                    print("Testing pod identity credentials with CWObject endpoint...")
                    client.s3_client.list_buckets()
                    print("Initialized CAIOS client using pod identity authentication and CWObject endpoint.")
                    return client
                except Exception as cwobject_e:
                    print(f"CWObject endpoint failed: {cwobject_e}")
            else:
                print(f"Pod identity authentication failed: {e}")

        try:
            print(f"Attempting access key authentication with {'LOTA' if use_lota else 'CAIOS'}...")
            client = AccessKeyObjectStorage(k8s, cw_token, use_lota, region)
            print("Testing access key credentials...")
            client.s3_client.list_buckets()
            print(f"Initialized CAIOS client using access key authentication ({'LOTA' if use_lota else 'CAIOS'}).")
            return client
        except Exception as e:
            # fallback to cwobject if lota isn't reachable from our location (local or non-gpu cluster)
            error_msg = str(e).lower()
            if use_lota and ("timeout" in error_msg or "connect" in error_msg):
                print(f"LOTA endpoint failed ({e})\n  Does your cluster have GPUs? Trying CWObject endpoint...")
                client = AccessKeyObjectStorage(k8s, cw_token, use_lota=False, region=region)
                print("Initialized CAIOS client using access key authentication (CAIOS).")
                return client
            else:
                # Re-raise if it's not a connection issue
                raise ObjectStorageError(f"Failed to create the ObjectStorage client: {e}")

    @staticmethod
    def with_pod_identity(
        k8s: K8s, cw_token: str = "", use_lota: bool = True, region: str = ""
    ) -> "PodIdentityObjectStorage":
        """Create ObjectStorage client using Pod Identity / Workload Identity.

        Use this when running in a CoreWeave Kubernetes cluster with pod identity configured.

        Args:
            k8s (K8s): Kubernetes client for interacting with the cluster
            cw_token (str, optional): CoreWeave API token. Will attempt to read from pod secrets if not provided.
            use_lota (bool, optional): Use LOTA endpoint. Defaults to True.
            region (str, optional): AWS region.

        Returns:
            PodIdentityObjectStorage: Authenticated client.

        Raises:
            MissingCredentialsError: If pod identity token is not available.
        """
        return PodIdentityObjectStorage(k8s, cw_token, use_lota, region)

    @staticmethod
    def with_access_keys(
        k8s: K8s, cw_token: str = "", use_lota: bool = True, region: str = ""
    ) -> "AccessKeyObjectStorage":
        """Create ObjectStorage client using Access Key authentication.

        Use this when running outside CoreWeave Kubernetes or with explicit credentials.
        Uses AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY or automatically generates key via CW_TOKEN.

        Args:
            k8s (K8s): Kubernetes client for interacting with the cluster
            cw_token (str, optional): CoreWeave API token for generating temporary keys.
            use_lota (bool, optional): Use LOTA endpoint. Defaults to True.
            region (str, optional): AWS region.

        Returns:
            AccessKeyObjectStorage: Authenticated client.

        Raises:
            MissingCredentialsError: If credentials cannot be obtained.
        """
        return AccessKeyObjectStorage(k8s, cw_token, use_lota, region)

    @abstractmethod
    def _fetch_temp_access_keys(self, duration_seconds: int = DEFAULT_ACCESS_TOKEN_DURATION) -> tuple[str, str]:
        """Generate temporary S3 access keys via CoreWeave API."""
        pass

    @property
    @abstractmethod
    def s3_client(self) -> S3Client:
        """Get the boto3 S3 client. Must be implemented by subclasses."""
        pass

    @property
    @abstractmethod
    def api_session(self) -> requests.Session:
        """Get HTTP session for CoreWeave API calls. Must be implemented by subclasses."""
        pass

    def list_buckets(self) -> list[str]:
        """List all S3 buckets.

        Returns:
            list[str]: List of bucket names. Returns empty list on error.
        """
        try:
            response = self.s3_client.list_buckets()
            buckets = response.get("Buckets", [])
            result = []
            for bucket in buckets:
                if name := bucket.get("Name"):
                    result.append(name)
            return result
        except Exception as e:
            print(f"Error listing buckets: {e}")
            return []

    def create_bucket(self, bucket_name: str) -> bool:
        """Create a new S3 bucket.

        Args:
            bucket_name (str): Name of the bucket to create.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            self.s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": self.region},
            )
            print(f"Created bucket: '{bucket_name}'")
            return True
        except Exception as e:
            print(f"Error creating bucket: {e}")
            return False

    def delete_bucket(self, bucket_name: str) -> bool:
        """Delete an empty S3 bucket.

        Args:
            bucket_name (str): Name of the bucket to delete.

        Returns:
            bool: True if successful, False otherwise.

        Note:
            Bucket must be empty. Use empty_bucket() first if needed.
        """
        try:
            self.s3_client.delete_bucket(Bucket=bucket_name)
            print(f"Deleted bucket '{bucket_name}'")
            return True
        except Exception as e:
            print(f"Error deleting bucket: {e}")
            return False

    def empty_bucket(self, bucket_name: str) -> bool:
        """Delete all objects in a bucket.

        Args:
            bucket_name (str): Name of the bucket to empty.

        Returns:
            bool: True if successful, False otherwise.

        Note:
            Deletes objects in batches of up to 1000. Warns about individual deletion failures.
        """
        try:
            print(f"Emptying bucket '{bucket_name}'...")
            total_deleted = 0
            continuation_token = None

            while True:
                list_result = self.list_objects(
                    bucket_name=bucket_name, continuation_token=continuation_token, max_keys=1000
                )
                objects = list_result.get("objects", [])
                if not objects:
                    break
                delete_keys = [{"Key": obj["Key"]} for obj in objects]
                resp = self.s3_client.delete_objects(Bucket=bucket_name, Delete={"Objects": delete_keys})
                deleted = len(resp.get("Deleted", []))
                total_deleted += deleted
                errors = resp.get("Errors", [])
                if errors:
                    print(f"Warning: {len(errors)} objects failed to delete")
                    for error in errors[:5]:
                        print(f"  - {error.get('Key')}: {error.get('Message')}")
                print(f"Deleted {deleted} objects (total: {total_deleted})")
                if not list_result.get("is_truncated"):
                    break
                continuation_token = list_result.get("next_continuation_token")
            print(f"Finished emptying bucket '{bucket_name}', total deleted: {total_deleted}")
            return True
        except Exception as e:
            print(f"Error emptying bucket: {e}")
            return False

    def put_bucket_policy(self, bucket_name: str, policy: dict[str, Any]) -> bool:
        """Apply an S3 bucket policy.

        Args:
            bucket_name (str): Name of the bucket.
            policy (dict[str, Any]): S3 bucket policy document.

        Returns:
            bool: True if successful, False otherwise.
        """
        policy_str = json.dumps(policy)
        try:
            self.s3_client.put_bucket_policy(Bucket=bucket_name, Policy=policy_str)
            print(f"Put bucket policy for bucket '{bucket_name}'")
            return True
        except Exception as e:
            print(f"Error putting bucket policy: {e}")
            return False

    def get_bucket_policy(self, bucket_name: str) -> dict[str, Any] | None:
        """Retrieve an S3 bucket policy.

        Args:
            bucket_name (str): Name of the bucket.

        Returns:
            dict[str, Any] | None: Parsed policy document, or None if not set or on error.
        """
        try:
            resp = self.s3_client.get_bucket_policy(Bucket=bucket_name)
            return json.loads(resp["Policy"])
        except Exception as e:
            print(f"Error getting bucket policy: {e}")
            return None

    def list_objects(
        self, bucket_name: str, prefix: str = "", max_keys: int = 1000, continuation_token: str | None = None
    ) -> dict[str, Any]:
        """List objects in a bucket with pagination support.

        Expected for consumers to loop over the function while passing in the continuation token.

        Args:
            bucket_name (str): Name of the bucket.
            prefix (str, optional): Filter objects by key prefix. Defaults to "".
            max_keys (int, optional): Maximum objects per request (capped at 1000). Defaults to 1000.
            continuation_token (str, optional): Token for paginated results.

        Returns:
            dict[str, Any]: Dictionary with keys:
                - "objects": List of object metadata dicts
                - "is_truncated": Whether more results exist
                - "next_continuation_token": Token for next page
                - "key_count": Number of objects in this response
        """
        try:
            params: dict[str, Any] = {
                "Bucket": bucket_name,
                "MaxKeys": min(max_keys, 1000),
            }
            if prefix:
                params["Prefix"] = prefix
            if continuation_token:
                params["ContinuationToken"] = continuation_token

            response = self.s3_client.list_objects_v2(**params)
            return {
                "objects": response.get("Contents", []),
                "is_truncated": response.get("IsTruncated", False),
                "next_continuation_token": response.get("NextContinuationToken"),
                "key_count": response.get("KeyCount", 0),
            }
        except Exception as e:
            print(f"Error listing objects in bucket '{bucket_name}': {e}")
            return {
                "objects": [],
                "is_truncated": False,
                "next_continuation_token": None,
                "key_count": 0,
            }


class PodIdentityObjectStorage(ObjectStorage):
    """ObjectStorage client using Kubernetes Pod Identity / Workload Identity.

    Automatically reads the pod identity token from the mounted secret and uses it
    for authentication with CoreWeave services.
    """

    def __init__(self, k8s: K8s, cw_token: str = "", use_lota: bool = True, region: str = ""):
        """Initialize Pod Identity client.

        Args:
            cw_token (str, optional): CoreWeave API token. If not provided, attempts to read
                from /var/run/secrets/cks.coreweave.com/serviceaccount/cks-pod-identity-token
            use_lota (bool, optional): Use LOTA endpoint. Defaults to True.
            region (str, optional): AWS region.
            k8s (K8s): The kubernetes client for interacting with the cluster

        Raises:
            MissingCredentialsError: If token file not found and no token provided.
        """
        if not cw_token:
            try:
                with open("/var/run/secrets/cks.coreweave.com/serviceaccount/cks-pod-identity-token") as f:
                    cw_token = f.read().strip()
            except FileNotFoundError:
                raise MissingCredentialsError(
                    "Pod identity token file not found, are you running in a CoreWeave cluster?"
                )
        super().__init__(k8s, cw_token, use_lota, region)

    @property
    def s3_client(self) -> S3Client:
        """Get or create the boto3 S3 client with pod identity authentication.

        Returns:
            S3Client: Cached boto3 S3 client instance.
        """
        if self._s3_client is None:
            self._s3_client = boto3.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url,
                config=self.s3_config,
            )
        return self._s3_client

    @property
    def api_session(self) -> requests.Session:
        """Get or create HTTP session for CW API with Bearer token auth.

        Returns:
            requests.Session: Cached session with Authorization header.
        """
        if self._api_session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.cw_token}",
                }
            )
            self._api_session = session
        return self._api_session

    def _fetch_temp_access_keys(self, duration_seconds: int = DEFAULT_ACCESS_TOKEN_DURATION) -> tuple[str, str]:
        """Generate temporary S3 access keys via CoreWeave API.

        Needed for warp benchmarking.

        Args:
            duration_seconds (int, optional): Key validity duration in seconds.

        Returns:
            tuple[str, str]: (access_key_id, secret_access_key)

        Raises:
            ObjectStorageError: If API request fails.
        """
        endpoint = f"{COREWEAVE_OBJECT_API_BASE_URL}/temporary-credentials/oidc"
        org_id = self.k8s.org_id
        payload = {"durationSeconds": duration_seconds, "orgId": org_id, "oidcToken": self.cw_token}

        try:
            resp = self.api_session.post(
                endpoint,
                json=payload,
            )
            resp.raise_for_status()

            data = resp.json()
            access_key_id = data.get("accessKeyId")
            secret_access_key = data.get("secretKey")
            if not access_key_id or not secret_access_key:
                raise ObjectStorageError("Invalid response from access key endpoint, missing keys.")

            return access_key_id, secret_access_key

        except requests.exceptions.RequestException as e:
            raise ObjectStorageError(f"Failed to create access key: {e}")


class AccessKeyObjectStorage(ObjectStorage):
    """ObjectStorage client using Access Key authentication.

    Supports both static keys (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY env vars)
    and temporary key generation via CW API using a CW_TOKEN.
    """

    def __init__(self, k8s: K8s, cw_token: str = "", use_lota: bool = True, region: str = ""):
        """Initialize Access Key client.

        Args:
            k8s (K8s): Kubernetes client for interacting with the cluster
            cw_token (str, optional): CoreWeave API token for key generation. Defaults to CW_TOKEN env var.
            use_lota (bool, optional): Use LOTA endpoint. Defaults to True.
            region (str, optional): AWS region.

        Raises:
            MissingCredentialsError: If no token provided and static keys not in environment.
        """
        super().__init__(k8s, cw_token, use_lota, region)
        if not self.cw_token:
            raise MissingCredentialsError("Missing cw_token, provide as function input or env var 'CW_TOKEN'.")

    @property
    def s3_client(self) -> S3Client:
        """Get or create the boto3 S3 client with access key authentication.

        Returns:
            S3Client: Cached boto3 S3 client instance.
        """
        if self._s3_client is None:
            self._s3_client = boto3.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url,
                config=self.s3_config,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
            )
        return self._s3_client

    @property
    def api_session(self) -> requests.Session:
        """Get or create HTTP session for CoreWeave API with Bearer token auth.

        Returns:
            requests.Session: Cached session with Authorization header.
        """
        if self._api_session is None:
            if not self.cw_token:
                raise MissingCredentialsError("Missing cw_token, provide as function input or env var 'CW_TOKEN'.")

            session = requests.Session()
            session.headers.update(
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.cw_token}",
                }
            )
            self._api_session = session
        return self._api_session

    def _fetch_temp_access_keys(self, duration_seconds: int = DEFAULT_ACCESS_TOKEN_DURATION) -> tuple[str, str]:
        """Generate temporary S3 access keys via CoreWeave API.

        Args:
            duration_seconds (int, optional): Key validity duration in seconds.

        Returns:
            tuple[str, str]: (access_key_id, secret_access_key)

        Raises:
            ObjectStorageError: If API request fails.
        """
        endpoint = f"{COREWEAVE_OBJECT_API_BASE_URL}/access-key"
        payload = {"durationSeconds": duration_seconds}

        try:
            resp = self.api_session.post(
                endpoint,
                json=payload,
            )
            resp.raise_for_status()

            data = resp.json()
            access_key_id = data.get("accessKeyId")
            secret_access_key = data.get("secretKey")
            if not access_key_id or not secret_access_key:
                raise ObjectStorageError("Invalid response from access key endpoint, missing keys.")

            print(f"Created access key: {access_key_id[:8]}")
            return access_key_id, secret_access_key

        except requests.exceptions.RequestException as e:
            raise ObjectStorageError(f"Failed to create access key: {e}")

    def list_org_policies(self) -> list[dict[str, Any]]:
        """List organization-level access policies from CW API.

            Can only be done with the non-oidc cw endpoints

        Returns:
            list[dict[str, Any]]: List of policy documents. Returns empty list on error.
        """
        try:
            resp = self.api_session.get(f"{COREWEAVE_OBJECT_API_BASE_URL}/access-policy")
            resp.raise_for_status()
            return resp.json().get(
                "policies",
            )
        except Exception as e:
            print(f"Error listing org policies: {e}")
            return []

    def apply_org_policy(self, policy: dict[str, Any]) -> bool:
        """Create or update an organization-level access policy.

        Can only be done with the non-oidc cw endpoints

        Args:
            policy (dict[str, Any]): Policy document with structure:
                {
                    "policy": {
                        "version": "v1alpha1",
                        "name": "policy-name",
                        "statements": [...]
                    }
                }

        Returns:
            bool: True if successful, False otherwise.
        """
        policy_name = policy.get("policy", {}).get("name", "unknown")

        try:
            response = self.api_session.post(
                f"{COREWEAVE_OBJECT_API_BASE_URL}/access-policy",
                json=policy,
            )
            response.raise_for_status()
            print(f"Applied organization policy: {policy_name}")
            return True
        except Exception as e:
            print(f"Error applying organization policy '{policy_name}': {e}")
            return False


def detect_region(k8s: K8s) -> str:
    """Autodetect CoreWeave region from environment or Kubernetes pod metadata.

    Checks in order:
    1. AWS_DEFAULT_REGION environment variable
    2. Kubernetes pod region annotation (for CW clusters)
    3. Defaults to empty string

    Args:
        k8s (K8s): Kubernetes client for interacting with the cluster
    Returns:
        str: Detected region name, or empty string if not found.

    Raises:
        MissingRegionError: When none of the methods for getting a region work.
    """
    region = os.environ.get("AWS_DEFAULT_REGION", "")
    if region:
        print(f"Detected region from env var: {region}")
    else:
        try:
            cluster_region = k8s.cluster_region
            if cluster_region:
                print(f"Detected region from cluster: {cluster_region}")
        except Exception as e:
            raise MissingRegionError(f"Unable to determine object storage region: {e}")
    return region
