import json
import os
from abc import ABC, abstractmethod
from logging import exception
from typing import TYPE_CHECKING, Any, Literal

import boto3
import requests
from botocore.config import Config

from arena.k8s import K8s

COREWEAVE_OBJECT_API_BASE_URL = "https://api.coreweave.com/v1/cwobject"
LOTA_ENDPOINT_URL = "https://cwlota.com"
CAIOS_ENDPOINT_URL = "https://cwobject.com"
DEFAULT_ACCESS_TOKEN_DURATION = 3600  # 1 hour
DEFAULT_ADDRESSING_STYLE = "virtual"

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
else:
    S3Client = object


class ObjectStorageError(Exception):
    """Base exception for ObjectStorage errors."""

    pass


class MissingCredentialsError(ObjectStorageError):
    """Raised when required credentials are missing"""

    pass


class MissingRegionError(ObjectStorageError):
    """Raised when unable to get a region"""

    pass


class ObjectStorage(ABC):
    """
    Abstract base class for CAIOS operations.
    Provides s3 access and org policy management.
    """

    def __init__(self, cw_token: str = "", use_lota: bool = True, region: str = ""):
        self.use_lota = use_lota
        self._s3_client: S3Client | None = None
        self._api_session: requests.Session | None = None
        self.region = region if region else detect_region()

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

    @staticmethod
    def auto(cw_token: str = "", use_lota: bool = True, region: str = "") -> "ObjectStorage":
        """
        Auto detect and create the ObjectStorage client
        Tries pod identity first with both lota and cwobject endpoints, and falls back to access keys with both lota and cwobject endpoints
        """
        print("Initializing CoreWeave AI object storage")
        # Choose our subclass with preference for PodIdentity if it works
        try:
            print(f"Attempting pod identity authentication with {'LOTA' if use_lota else 'CAIOS'}...")
            client = PodIdentityObjectStorage(cw_token, use_lota, region)
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
                    client = PodIdentityObjectStorage(cw_token, use_lota=False, region=region)
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
            client = AccessKeyObjectStorage(cw_token, use_lota, region)
            print("Testing access key credentials...")
            client.s3_client.list_buckets()
            print(f"Initialized CAIOS client using access key authentication ({'LOTA' if use_lota else 'CAIOS'}).")
            return client
        except Exception as e:
            # fallback to cwobject if lota isn't reachable from our location (local or non-gpu cluster)
            error_msg = str(e).lower()
            if use_lota and ("timeout" in error_msg or "connect" in error_msg):
                print(f"LOTA endpoint failed ({e})\n  Does your cluster have GPUs? Trying CWObject endpoint...")
                client = AccessKeyObjectStorage(cw_token, use_lota=False, region=region)
                print("Initialized CAIOS client using access key authentication (CAIOS).")
                return client
            else:
                # Re-raise if it's not a connection issue
                raise

    @staticmethod
    def with_pod_identity(cw_token: str = "", use_lota: bool = True, region: str = "") -> "PodIdentityObjectStorage":
        """
        Create ObjectStorage client using Pod Identity / Workload Identity authentication.
        """
        return PodIdentityObjectStorage(cw_token, use_lota, region)

    @staticmethod
    def with_access_keys(cw_token: str = "", use_lota: bool = True, region: str = "") -> "AccessKeyObjectStorage":
        """
        Create ObjectStorage client using Access Key authentication.
        """
        return AccessKeyObjectStorage(cw_token, use_lota, region)

    @property
    @abstractmethod
    def s3_client(self) -> S3Client:
        "Get the boto3 s3 client"
        pass

    @property
    @abstractmethod
    def api_session(self) -> requests.Session:
        "Get http session for cwobject api"
        pass

    def list_buckets(self) -> list[str]:
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
        try:
            self.s3_client.delete_bucket(Bucket=bucket_name)
            print(f"Deleted bucket '{bucket_name}'")
            return True
        except Exception as e:
            print(f"Error deleting bucket: {e}")
            return False

    def empty_bucket(self, bucket_name: str) -> bool:
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
        policy_str = json.dumps(policy)
        try:
            self.s3_client.put_bucket_policy(Bucket=bucket_name, Policy=policy_str)
            print(f"Put bucket policy for bucket '{bucket_name}'")
            return True
        except Exception as e:
            print(f"Error putting bucket policy: {e}")
            return False

    def get_bucket_policy(self, bucket_name: str) -> dict[str, Any] | None:
        try:
            resp = self.s3_client.get_bucket_policy(Bucket=bucket_name)
            return json.loads(resp["Policy"])
        except Exception as e:
            print(f"Error getting bucket policy: {e}")
            return None

    def list_org_policies(self) -> list[dict[str, Any]]:
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
        """
        Example:
            policy = {
                "policy": {
                    "version": "v1alpha1",
                    "name": "my-policy",
                    "statements": [{
                        "name": "allow-full-access",
                        "effect": "Allow",
                        "actions": ["s3:*"],
                        "resources": ["*"],
                        "principals": ["role/Admin"]
                    }]
                }
            }
            storage.apply_organization_policy(policy)
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

    def list_objects(
        self, bucket_name: str, prefix: str = "", max_keys: int = 1000, continuation_token: str | None = None
    ) -> dict[str, Any]:
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
    """
    ObjectStorage client using Pod Identity / Workload Identity authentication.
    """

    def __init__(self, cw_token: str = "", use_lota: bool = True, region: str = ""):
        super().__init__(cw_token, use_lota, region)

    @property
    def s3_client(self) -> S3Client:
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
        if not self.cw_token:
            with open("/var/run/secrets/cks.coreweave.com/serviceaccount/cks-pod-identity-token") as f:
                self.cw_token = f.read().strip()
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


class AccessKeyObjectStorage(ObjectStorage):
    """
    ObjectStorage client using Access Key authentication.
    Expects CW_TOKEN to be set in the environment.
    If AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY is not set, uses the CW_TOKEN to create a temporary access key pair.
    """

    def __init__(self, cw_token: str = "", use_lota: bool = True, region: str = ""):
        super().__init__(cw_token, use_lota, region)
        self._access_key_id: str | None = None
        self._secret_access_key: str | None = None
        if not self.cw_token:
            raise MissingCredentialsError("Missing cw_token, provide as function input or env var 'CW_TOKEN'.")

    @property
    def s3_client(self) -> S3Client:
        if self._s3_client is None:
            access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
            secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")

            # Create if not provided in env
            if not (access_key_id and secret_access_key):
                print("Creating access keys")
                access_key_id, secret_access_key = self._get_temp_access_keys()
                self._access_key_id = access_key_id
                self._secret_access_key = secret_access_key

            self._s3_client = boto3.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url,
                config=self.s3_config,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
            )
        return self._s3_client

    @property
    def api_session(self) -> requests.Session:
        if self._api_session is None:
            if not self.cw_token:
                raise ValueError("Missing cw_token, provide as function input or env var 'CW_TOKEN'.")

            session = requests.Session()
            session.headers.update(
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.cw_token}",
                }
            )
            self._api_session = session
        return self._api_session

    def _get_temp_access_keys(self, duration_seconds: int = DEFAULT_ACCESS_TOKEN_DURATION) -> tuple[str, str]:
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
                raise ValueError("Invalid response from access key endpoint, missing keys.")

            print(f"Created access key: {access_key_id[:8]}")
            return access_key_id, secret_access_key

        except requests.exceptions.RequestException as e:
            raise ValueError(f"Failed to create access key: {e}")


def detect_region() -> str:
    region = os.environ.get("AWS_DEFAULT_REGION", "")
    if region:
        print(f"Detected region from env var: {region}")
    else:
        pod_region = K8s().get_pod_region()
        if pod_region:
            region = (
                f"{pod_region}A"  # suffix with 'A'; hacky shit since we can't tell what az we're in from in-cluster
            )
            print(f"Detected region from pod: {region}")
        else:
            raise MissingRegionError(
                "Unable to determine object storage region, provide as function input or env var 'AWS_DEFAULT_REGION'."
            )
    return region
