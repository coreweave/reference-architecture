import json
import os
from abc import ABC, abstractmethod
from logging import exception
from typing import TYPE_CHECKING, Any, Literal

import boto3
import requests
from botocore.config import Config

COREWEAVE_OBJECT_API_BASE_URL = "https://api.coreweave.com/v1/cwobject"
LOTA_ENDPOINT_URL = "https://cwlota.com"
CAIOS_ENDPOINT_URL = "https://cwobject.com"
DEFAULT_ACCESS_TOKEN_DURATION = 3600  # 1 hour

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


class ObjectStorage(ABC):
    """
    Abstract base class for CAIOS operations.
    Provides s3 access and org policy management.
    """

    def __init__(self, cw_token: str = "", use_lota: bool = True, region: str = ""):
        self.use_lota = use_lota
        self.region = region if region else os.environ.get("AWS_DEFAULT_REGION", "")
        self._s3_client: S3Client | None = None
        self._api_session: requests.Session | None = None
        self.endpoint_url = LOTA_ENDPOINT_URL if self.use_lota else CAIOS_ENDPOINT_URL

        style = os.environ.get("AWS_S3_ADDRESSING_STYLE", "path")
        self.addressing_style: Literal["path", "virtual", "auto"] = (
            style if style in ("path", "virtual", "auto") else "path"
        )

        self.cw_token = cw_token if cw_token else os.environ.get("CW_TOKEN", "")

    @staticmethod
    def auto(cw_token: str = "", use_lota: bool = True) -> "ObjectStorage":
        """
        Auto detect and create the ObjectStorage client
        Tries pod identity first, and falls back to access keys
        """

        try:
            client = PodIdentityObjectStorage(cw_token, use_lota)
            client.s3_client.list_buckets()
            print("Initialized CAIOS client using pod identity authentication.")
            return client
        except Exception:
            client = AccessKeyObjectStorage(cw_token, use_lota)
            print("Initialized CAIOS client using cw_token and access keys.")
            return client

    @staticmethod
    def with_pod_identity(cw_token: str = "", use_lota: bool = True) -> "PodIdentityObjectStorage":
        """
        Create ObjectStorage client using Pod Identity / Workload Identity authentication.
        """
        return PodIdentityObjectStorage(cw_token, use_lota)

    @staticmethod
    def with_access_keys(cw_token: str = "", use_lota: bool = True) -> "AccessKeyObjectStorage":
        """
        Create ObjectStorage client using Access Key authentication.
        """
        return AccessKeyObjectStorage(cw_token, use_lota)

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
            self.s3_client.create_bucket(Bucket=bucket_name)
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
        except exception as e:
            print(f"Error deleting bucket: {e}")
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


class PodIdentityObjectStorage(ObjectStorage):
    """
    ObjectStorage client using Pod Identity / Workload Identity authentication.
    """

    @property
    def s3_client(self) -> S3Client:
        if self._s3_client is None:
            s3_config = Config(s3={"addressing_style": self.addressing_style})
            self._s3_client = boto3.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url,
                config=s3_config,
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

    def __init__(self, cw_token: str = "", use_lota: bool = True):
        super().__init__(cw_token=cw_token, use_lota=use_lota)
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

            s3_config = Config(s3={"addressing_style": self.addressing_style})
            self._s3_client = boto3.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url,
                config=s3_config,
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
