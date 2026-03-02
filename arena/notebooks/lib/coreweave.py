import os

import marimo as mo
import requests
from kubernetes import config
from kubernetes.client.configuration import Configuration


def validate_cw_token(token: str) -> int:
    """Checks that the token is valid for the /cks/clusters endpoint.

    Does not validate that the token can access all endpoints, intended mostly as a basic check the token is not expired.

    Returns:
        Response status code.
    """
    response: requests.Response = requests.get(
        "http://api.coreweave.com/v1beta1/cks/clusters",
        headers={"Authorization": f"Bearer {token}"},
        timeout=2,
    )
    return response.status_code


def detect_cw_token(kubeconfig_path: str = "", context: str = "") -> str:  # noqa: C901
    """Detects the cw_token from various sources.

    Attempts to find token in the following order:
    1. CW_TOKEN environment variable
    2. AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE (pod identity)
    3. Kubeconfig file (if path provided)

    Args:
        kubeconfig_path: Path to kubeconfig file. If empty, tries KUBECONFIG env var.
        context: If multiple contexts, specify which one. Else falls back to currently active context.

    Returns:
        str: The detected token or empty string if not found.
    """
    # 1. Check CW_TOKEN env var
    cw_token = os.getenv("CW_TOKEN")
    if cw_token and validate_cw_token(cw_token) == 200:
        return cw_token

    # 2. Check pod identity auth
    token_file = os.getenv("AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE")
    if token_file and os.path.exists(token_file):
        try:
            with open(token_file, "r") as f:
                token = f.read().strip()
                if validate_cw_token(token) == 200:
                    return token
        except Exception:
            pass

    # 3. Check kubeconfig file
    if not kubeconfig_path:
        kubeconfig_path = os.getenv("KUBECONFIG", "")

    if not kubeconfig_path or not os.path.exists(os.path.expanduser(kubeconfig_path)):
        return ""

    try:
        contexts, active_context = config.list_kube_config_contexts(config_file=kubeconfig_path)

        # Use specified context or active context
        if context:
            target_context = next((ctx for ctx in contexts if ctx["name"] == context), None)
        else:
            target_context = active_context

        if not target_context:
            return ""

        loader = config.kube_config._get_kube_config_loader(
            filename=kubeconfig_path, active_context=target_context["name"]
        )
        loader.load_and_set(Configuration())

        user_name = target_context["context"]["user"]
        user_config = {}
        for user in loader._config.safe_get("users") or []:
            if user.safe_get("name") == user_name:
                user_config = user.safe_get("user") or {}
                break

        if not user_config:
            return ""

        # Check for token directly in config
        if "token" in user_config:
            token = user_config["token"]
            if validate_cw_token(token) == 200:
                return token

        # Check for tokenFile reference
        elif "tokenFile" in user_config:
            token_file_path = user_config["tokenFile"]
            with open(os.path.expanduser(token_file_path), "r") as f:
                token = f.read().strip()
                if validate_cw_token(token) == 200:
                    return token

        return ""

    except Exception:
        # Silently return "" if kubeconfig detection fails
        return ""


def cw_token_input() -> tuple[mo.Html | None, mo.ui.form | None]:
    """Create a form for a user to input their CW_TOKEN secret for auth.

    To access the token in your code, use token_form.value.get("cw_token")
    """
    token_form = (
        mo.md("{cw_token}")
        .batch(cw_token=mo.ui.text(kind="password", placeholder="CW-SECRET-...", full_width=True))  # type: ignore
        .form(submit_button_label="Connect", bordered=False)
    )
    token_ui = mo.md(
        f"""
        /// admonition | Manual Initialization Required
            type: warning

        Automatic CoreWeave credentials not found. Please enter your [CoreWeave access token](https://console.coreweave.com/tokens) to initialize the ObjectStorage client.
        ///

        {token_form}
        """
    )
    return token_ui, token_form
