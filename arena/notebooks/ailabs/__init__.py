"""
AILabs - Helper utilities for CoreWeave infrastructure.

Modules:
    remote_execution_helpers: SSH helpers for running commands on remote hosts
    object_storage_helpers: CoreWeave AI Object Storage policy management

Usage:
    from ailabs.remote_execution_helpers import ssh, run_remote
    from ailabs.object_storage_helpers import apply_policy, list_policies
    
    # Or import modules
    from ailabs import remote_execution_helpers, object_storage_helpers
"""

from ailabs import remote_execution_helpers
from ailabs import object_storage_helpers

# Expose commonly used functions at package level
from ailabs.remote_execution_helpers import ssh, run_remote, run_remote_interactive
from ailabs.object_storage_helpers import (
    apply_policy,
    list_policies,
    delete_policy,
    get_s3_client,
    list_buckets,
)

__all__ = [
    # Modules
    "remote_execution_helpers",
    "object_storage_helpers",
    # SSH functions
    "ssh",
    "run_remote",
    "run_remote_interactive",
    # Object storage functions
    "apply_policy",
    "list_policies",
    "delete_policy",
    "get_s3_client",
    "list_buckets",
]
