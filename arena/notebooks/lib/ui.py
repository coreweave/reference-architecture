import marimo as mo
from marimo import Html

"""Reusable UI components for CoreWeave ARENA Marimo notebooks.

This module provides a collection of standardized UI components that can be reused
across different ARENA notebooks to maintain consistent styling and functionality.

Example Usage:
    Basic notebook header setup:
        ```python
        from lib.reusable_cells import banner, about, table_of_contents

        @app.cell(hide_code=True)
        def _():
            _elements = mo.vstack([
                banner(),
                about("My Notebook", "Description of what this notebook does"),
                table_of_contents([
                    {"title": "Section 1", "description": "First section"},
                    {"title": "Section 2", "description": "Second section"}
                ])
            ])

            mo.vstack(_elements)
            return
        ```
"""


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
