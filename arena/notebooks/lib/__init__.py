"""Arena - Helper utilities for CoreWeave infrastructure.

Modules:
    remote_execution_helpers: SSH helpers for running commands on remote hosts
    object_storage: CoreWeave AI Object Storage management

Usage:
    from lib.remote_execution_helpers import ssh, run_remote
    from lib.object_storage import apply_policy, list_policies

    # Or import modules
    from lib import remote_execution_helpers, object_storage
"""

# SSH functions
from lib.remote_execution_helpers import run_remote, run_remote_interactive, ssh

from . import remote_execution_helpers

__all__ = [
    # Modules
    "remote_execution_helpers",
    "object_storage_helpers",
    # SSH functions
    "ssh",
    "run_remote",
    "run_remote_interactive",
]
