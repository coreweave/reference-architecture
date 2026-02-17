"""
CoreWeave AI Object Storage Policy Helpers.

Simple helpers for applying and retrieving organization access policies.

Reference: https://docs.coreweave.com/docs/products/storage/object-storage/auth-access/organization-policies/examples

Environment Variables (expected from Kubernetes secrets):
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - AWS_DEFAULT_REGION
    - S3_ENDPOINT_URL
    - LOTA_ENDPOINT_URL
    - AWS_S3_ADDRESSING_STYLE
    - API_ACCESS_TOKEN (for organization policy management)

Usage:
    from arena.object_storage_helpers import apply_policy, get_policy, list_policies
    
    # Apply a policy from JSON string
    policy_json = '''
    {
      "policy": {
        "version": "v1alpha1",
        "name": "full-s3-api-access",
        "statements": [
          {
            "name": "allow-full-s3-api-access-to-all",
            "effect": "Allow",
            "actions": ["s3:*"],
            "resources": ["*"],
            "principals": ["role/Admin"]
          }
        ]
      }
    }
    '''
    apply_policy(policy_json)
    
    # Get a specific policy
    policy = get_policy("full-s3-api-access")
    
    # List all policies
    policies = list_policies()
"""

import os
import json
from typing import Dict, List, Any, Optional, Union


# =============================================================================
# Configuration
# =============================================================================

def get_config() -> Dict[str, str]:
    """
    Get configuration from environment variables.
    
    Returns:
        Dictionary with configuration values
        
    Raises:
        EnvironmentError: If required environment variables are not set
    """
    required_vars = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
        "S3_ENDPOINT_URL",
    ]
    
    config = {}
    missing = []
    
    for var in required_vars:
        value = os.environ.get(var)
        if not value:
            missing.append(var)
        else:
            config[var] = value
    
    # Optional variables
    config["LOTA_ENDPOINT_URL"] = os.environ.get("LOTA_ENDPOINT_URL", "")
    config["AWS_S3_ADDRESSING_STYLE"] = os.environ.get("AWS_S3_ADDRESSING_STYLE", "path")
    
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")
    
    return config


def _get_api_session():
    """
    Create an HTTP session for CoreWeave Object Storage API.
    
    Uses Bearer token authentication with API_ACCESS_TOKEN environment variable.
    
    Returns:
        Tuple of (requests.Session, config dict)
        
    Raises:
        EnvironmentError: If API_ACCESS_TOKEN is not set
    """
    import requests
    
    config = get_config()
    
    api_token = os.environ.get("API_ACCESS_TOKEN")
    if not api_token:
        raise EnvironmentError("Missing required environment variable: API_ACCESS_TOKEN")
    
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}",
    })
    
    return session, config


# CoreWeave Organization Policy API endpoint
COREWEAVE_API_BASE_URL = "https://api.coreweave.com/v1/cwobject"


def _get_api_base_url() -> str:
    """
    Get the base URL for the CoreWeave Object Storage API.
    """
    return COREWEAVE_API_BASE_URL


# =============================================================================
# Policy API
# =============================================================================

def list_policies() -> List[Dict[str, Any]]:
    """
    List all organization access policies.
    
    Returns:
        List of policy objects
        
    Example:
        policies = list_policies()
        for p in policies:
            print(p["policy"]["name"])
    """
    session, _ = _get_api_session()
    base_url = _get_api_base_url()
    
    try:
        response = session.get(f"{base_url}/access-policy")
        response.raise_for_status()
        return response.json().get("policies", [])
    except Exception as e:
        print(f"Error listing policies: {e}")
        return []


def apply_policy(policy: Union[str, Dict[str, Any]]) -> bool:
    """
    Apply (create/update) an organization access policy.
    
    Uses the CoreWeave API: POST https://api.coreweave.com/v1/cwobject/access-policy
    
    Args:
        policy: Policy as JSON string or dict (must include "policy" wrapper)
        
    Returns:
        True if successful, False otherwise
        
    Example:
        apply_policy('''
        {
          "policy": {
            "version": "v1alpha1",
            "name": "my-policy",
            "statements": [
              {
                "name": "allow-full-access",
                "effect": "Allow",
                "actions": ["s3:*"],
                "resources": ["*"],
                "principals": ["role/Admin"]
              }
            ]
          }
        }
        ''')
    """
    session, _ = _get_api_session()
    base_url = _get_api_base_url()
    
    # Parse JSON string if needed
    if isinstance(policy, str):
        try:
            policy = json.loads(policy)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            return False
    
    policy_name = policy.get("policy", {}).get("name", "unknown")
    
    try:
        response = session.post(
            f"{base_url}/access-policy",
            json=policy,
        )
        response.raise_for_status()
        print(f"Successfully applied policy: {policy_name}")
        return True
    except Exception as e:
        print(f"Error applying policy '{policy_name}': {e}")
        return False


def delete_policy(policy_name: str) -> bool:
    """
    Delete an organization access policy.
    
    Note: Delete endpoint not explicitly documented. Use Cloud Console if this fails.
    
    Args:
        policy_name: Name of the policy to delete
        
    Returns:
        True if successful, False otherwise
    """
    session, _ = _get_api_session()
    base_url = _get_api_base_url()
    
    # Try DELETE on the policy endpoint - not explicitly documented
    try:
        response = session.delete(f"{base_url}/access-policy/{policy_name}")
        response.raise_for_status()
        print(f"Successfully deleted policy: {policy_name}")
        return True
    except Exception as e:
        print(f"Error deleting policy '{policy_name}': {e}")
        print("Note: Delete via API may not be supported. Use Cloud Console instead.")
        return False


# =============================================================================
# S3 Client Helper
# =============================================================================

def get_s3_client(use_lota: bool = False):
    """
    Create an S3 client using environment configuration.
    
    Args:
        use_lota: If True, use LOTA_ENDPOINT_URL instead of S3_ENDPOINT_URL
        
    Returns:
        boto3 S3 client
    """
    import boto3
    from botocore.config import Config
    
    config = get_config()
    
    endpoint_url = config["LOTA_ENDPOINT_URL"] if use_lota else config["S3_ENDPOINT_URL"]
    if not endpoint_url:
        endpoint_url = config["S3_ENDPOINT_URL"]
    
    s3_config = Config(
        s3={"addressing_style": config["AWS_S3_ADDRESSING_STYLE"]}
    )
    
    return boto3.client(
        "s3",
        aws_access_key_id=config["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=config["AWS_SECRET_ACCESS_KEY"],
        region_name=config["AWS_DEFAULT_REGION"],
        endpoint_url=endpoint_url,
        config=s3_config,
    )


def create_bucket(bucket_name: str, use_lota: bool = False) -> bool:
    """
    Create an S3 bucket (S3-compatible; e.g. CoreWeave CAIOS/LOTA).
    
    Args:
        bucket_name: Name for the new bucket (must be globally unique).
        use_lota: If True, use LOTA endpoint.
        
    Returns:
        True if the bucket was created or already exists, False on error.
    """
    if not bucket_name or not bucket_name.strip():
        print("Error: bucket name is required")
        return False
    bucket_name = bucket_name.strip()
    config = get_config()
    region = config.get("AWS_DEFAULT_REGION", "us-east-1")
    s3 = get_s3_client(use_lota=use_lota)
    try:
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": region},
        )
        print(f"Created bucket: {bucket_name}")
        return True
    except s3.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou"):
            print(f"Bucket already exists: {bucket_name}")
            return True
        # Some S3-compatible endpoints don't support LocationConstraint; try without
        if code in ("InvalidLocationConstraint", "IllegalLocationConstraintException"):
            try:
                s3.create_bucket(Bucket=bucket_name)
                print(f"Created bucket: {bucket_name}")
                return True
            except s3.exceptions.ClientError as e2:
                code2 = e2.response.get("Error", {}).get("Code", "")
                if code2 in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou"):
                    print(f"Bucket already exists: {bucket_name}")
                    return True
                print(f"Error creating bucket: {e2}")
                return False
        print(f"Error creating bucket: {e}")
        return False
    except Exception as e:
        print(f"Error creating bucket: {e}")
        return False


def list_buckets(use_lota: bool = False) -> List[str]:
    """
    List all available S3 buckets.
    
    Args:
        use_lota: If True, use LOTA endpoint
        
    Returns:
        List of bucket names
    """
    s3 = get_s3_client(use_lota=use_lota)
    
    try:
        response = s3.list_buckets()
        return [bucket["Name"] for bucket in response.get("Buckets", [])]
    except Exception as e:
        print(f"Error listing buckets: {e}")
        return []
