"""Reusable authentication helpers for Marimo notebooks.

This module provides functions that return tuples of UI and state for K8s and ObjectStorage
authentication, allowing notebooks to handle auth with minimal boilerplate.
"""

import marimo as mo

from .coreweave import cw_token_input, detect_cw_token
from .k8s import K8s, KubernetesConfigError, kubeconfig_input
from .storage.object_storage import MissingCredentialsError, ObjectStorage


def init_k8s() -> tuple[K8s | None, mo.ui.form | None, mo.Html | None]:
    """Initialize K8s client with auto-detection and fallback to manual input.

    Returns:
        tuple: (k8s_client, kubeconfig_form, ui_element)
            - k8s_client: K8s instance if successful, None otherwise
            - kubeconfig_form: Form for manual kubeconfig input, None if auto-init succeeded
            - ui_element: UI to display (form or None)

    Usage in a Marimo cell:
        ```python
        @app.cell(hide_code=True)
        def _():
            k8s, kubeconfig_form, _ui = init_k8s()
            _ui
            return k8s, kubeconfig_form
        ```
    """
    kubeconfig_form = None
    k8s = None
    _ui = None

    try:
        k8s = K8s()
        _ui = mo.md("Kubernetes client initialized")
    except KubernetesConfigError:
        _kubeconfig_ui, kubeconfig_form = kubeconfig_input()
        _ui = _kubeconfig_ui

    return k8s, kubeconfig_form, _ui


def process_k8s_form(k8s: K8s | None, kubeconfig_form: mo.ui.form | None) -> tuple[K8s | None, list[mo.Html]]:
    """Process manual kubeconfig input form if auto-init failed.

    Args:
        k8s: K8s client from init_k8s() or None
        kubeconfig_form: Form from init_k8s() or None

    Returns:
        tuple: (k8s_client, messages)
            - k8s_client: K8s instance (original or newly created)
            - messages: List of UI messages to display

    Usage in a Marimo cell:
        ```python
        @app.cell(hide_code=True)
        def _(k8s, kubeconfig_form):
            k8s_client, _msgs = process_k8s_form(k8s, kubeconfig_form)
            mo.output.append(mo.vstack(_msgs)) if _msgs else None
            return (k8s_client,)
        ```
    """
    k8s_client = k8s
    messages = []

    if kubeconfig_form is not None:
        if k8s_client is None and kubeconfig_form.value:
            kubeconfig_path = kubeconfig_form.value.get("kubeconfig_path")
            if kubeconfig_path:
                try:
                    k8s_client = K8s(kubeconfig_path=kubeconfig_path)
                    messages.append(mo.md(f"Loaded kubeconfig from `{kubeconfig_path}`"))
                except Exception as e:
                    messages.append(mo.md(f"Failed to initialize K8s client: {e}"))

    return k8s_client, messages


def init_object_storage(
    k8s_client: K8s | None,
) -> tuple[ObjectStorage | None, mo.ui.form | None, mo.Html | None]:
    """Initialize ObjectStorage client with auto-detection and fallback to manual input.

    Args:
        k8s_client: K8s client instance (required)

    Returns:
        tuple: (storage_client, cw_token_form, ui_element)
            - storage_client: ObjectStorage instance if successful, None otherwise
            - cw_token_form: Form for manual token input, None if auto-init succeeded
            - ui_element: UI to display (form or None)

    Usage in a Marimo cell:
        ```python
        @app.cell(hide_code=True)
        def _(k8s_client):
            storage, cw_token_form, _ui = init_object_storage(k8s_client)
            _ui
            return storage, cw_token_form
        ```
    """
    cw_token_form = None
    storage = None
    _ui = None

    if k8s_client:
        auto_cw_token = detect_cw_token(k8s_client.kubeconfig_path) if k8s_client.kubeconfig_path else detect_cw_token()

        try:
            storage = ObjectStorage.auto(k8s=k8s_client, cw_token=auto_cw_token)
            _ui = mo.md("ObjectStorage client initialized")
        except MissingCredentialsError:
            _cw_token_ui, cw_token_form = cw_token_input()
            _ui = _cw_token_ui

    return storage, cw_token_form, _ui


def process_storage_form(
    storage: ObjectStorage | None,
    cw_token_form: mo.ui.form | None,
    k8s_client: K8s | None,
) -> tuple[ObjectStorage | None, list[mo.Html]]:
    """Process manual CW token input form if auto-init failed.

    Args:
        storage: ObjectStorage client from init_object_storage() or None
        cw_token_form: Form from init_object_storage() or None
        k8s_client: K8s client instance (required)

    Returns:
        tuple: (storage_client, messages)
            - storage_client: ObjectStorage instance (original or newly created)
            - messages: List of UI messages to display

    Usage in a Marimo cell:
        ```python
        @app.cell(hide_code=True)
        def _(storage, cw_token_form, k8s_client):
            storage_client, _msgs = process_storage_form(storage, cw_token_form, k8s_client)
            mo.output.append(mo.vstack(_msgs)) if _msgs else None
            return (storage_client,)
        ```
    """
    storage_client = storage
    messages = []

    if cw_token_form is not None:
        if storage_client is None and cw_token_form.value:
            cw_token = cw_token_form.value.get("cw_token")
            if cw_token and k8s_client:
                try:
                    storage_client = ObjectStorage.auto(k8s=k8s_client, cw_token=cw_token)
                    messages.append(mo.md("ObjectStorage client initialized"))
                except Exception as e:
                    messages.append(mo.md(f"Failed to initialize ObjectStorage client: {e}"))

    return storage_client, messages
