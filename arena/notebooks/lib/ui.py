"""Reusable UI components for CoreWeave ARENA Marimo notebooks.

This module provides a collection of standardized UI components that can be reused
across different ARENA notebooks to maintain consistent styling and functionality.
"""

import marimo as mo
from marimo import Html


def banner() -> Html:
    """Create an image using the ARENA banner."""
    header = mo.md(r"""
    ![CoreWeave ARENA Banner](public/banner.jpg)
    """)
    return header


def about(title: str, details: str) -> Html:
    """Create an about for the notebook.

    Will be prefixed with `CoreWeave ARENA:`
    """
    about = mo.md(f"""
    # CoreWeave ARENA: {title}

    /// admonition | About This Notebook
        type: info

    {details}
    ///
    """)
    return about


def table_of_contents(items: list[dict[str, str]]) -> Html:
    """Create a clickable table of contents.

    Args:
        items: List of dictionaries with 'title' and 'description' keys.
               The title will be converted to an anchor link automatically.
               Example: [
                   {"title": "Bucket Operations", "description": "List and manage buckets"},
                   {"title": "Warp Benchmark", "description": "Multinode cluster benchmarking"}
               ]

    Returns:
        Html: Marimo HTML object with clickable table of contents.
    """
    toc_items = []
    for item in items:
        title = item["title"]
        description = item.get("description", "")

        # Convert title to anchor ID
        anchor = title.lower().replace(" ", "-").replace("/", "-").replace("&", "").replace("--", "-").strip("-")

        link_text = f"[**{title}**](#{anchor})"
        if description:
            toc_items.append(f"- {link_text} - {description}")
        else:
            toc_items.append(f"- {link_text}")

    toc_content = "\n".join(toc_items)

    table = mo.md(f"""
/// details | Table of Contents
    type: info

{toc_content}
///
""")
    return table


def security_disclaimer() -> Html:
    """Provides the standard security boilerplate."""
    return mo.md("""
        /// details | Security Disclaimer
            type: warning

        **CoreWeave Kubernetes Service:**
        Please note that this notebook operates using a Kubernetes service account with the following default permissions within its namespace:
        - Read access to Pods (view pod details and status)
        - Read access to Pod logs
        - Permission to execute commands inside Pods (kubectl exec–equivalent access)
        - Read access to Services
        - Read access to ConfigMaps
        - Read access to PersistentVolumeClaims
        - Read access to Deployments, StatefulSets, and ReplicaSets
        - Read access to Jobs

        In addition, the service account has the following cluster-wide permission:
        - Read access to Node metadata (view node details such as labels, status, and capacity)

        **CoreWeave AI Object Storage:**

        The service account has the following permissions for Object Storage:
        - Create short-lived access keys (enables the pod to generate its own short-lived access keys for interacting with Object Storage)
        - Perform any action on buckets (includes creating and deleting buckets, putting and getting objects, etc)

        **Important Note:**

        Within the CKS cluster, no write, delete, or modify permissions are granted by default beyond the ability to execute commands inside existing pods. Any user with access to the provided token can execute actions at the access level granted to this service account, including running commands inside pods in the namespace.
        ///
        """)
