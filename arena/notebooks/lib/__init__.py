"""Arena - Helper utilities for CoreWeave infrastructure.

Modules:
    remote_execution_helpers: SSH helpers for running commands on remote hosts
    object_storage_helpers: CoreWeave AI Object Storage policy management

Usage:
    from arena.remote_execution_helpers import ssh, run_remote
    from arena.object_storage_helpers import apply_policy, list_policies

    # Or import modules
    from arena import remote_execution_helpers, object_storage_helpers
"""

# SSH functions
from lib.remote_execution_helpers import run_remote, run_remote_interactive, ssh
from lib.storage.object_storage_helpers import (
    MissingCredentialsError,
    ObjectStorage,
)

from . import remote_execution_helpers
from .storage import object_storage_helpers

__all__ = [
    # Modules
    "remote_execution_helpers",
    "object_storage_helpers",
    # SSH functions
    "ssh",
    "run_remote",
    "run_remote_interactive",
    # Object Storage
    "ObjectStorage",
    "MissingCredentialsError",
]
