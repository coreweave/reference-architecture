import os

import marimo as mo
import requests
from kubernetes import config
from kubernetes.client.configuration import Configuration


def validate_cw_token(token: str) -> int:
    """Checks that the token is valid for the /cks/clusters endpoint.

    Does not validate that the token can access all endpoints.

    Returns:
        Response status code.
    """
    response: requests.Response = requests.get(
        "http://api.coreweave.com/v1beta1/cks/clusters",
        headers={"Authorization": f"Bearer {token}"},
        timeout=2,
    )
    return response.status_code


def detect_cw_token(context: str = "") -> str | None:  # noqa: C901
    """Detects the cw_token from various sources.

    Attempts to find token in the following order:
    1. CW_TOKEN environment variable
    2. AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE (pod identity)
    4. Kubeconfig file
    Args:
        kubeconfig_path: Path local to notebook where the kubeconfig can be found.
        context: If multiple contexts, specify which one. Else falls back to currently active context.

    Returns:
        str | None: The detected token or None if not found.
    """
    # 1. Check CW_TOKEN env var
    cw_token = os.getenv("CW_TOKEN")
    if cw_token:
        token = cw_token
        if validate_cw_token(token) == 200:
            return token

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
    kubeconfig_path = os.getenv("KUBECONFIG", "")
    if not kubeconfig_path or not os.path.exists(os.path.expanduser(kubeconfig_path)):
        return None

    try:
        contexts, active_context = config.list_kube_config_contexts(config_file=kubeconfig_path)

        # Use specified context or active context
        if context:
            target_context = next((ctx for ctx in contexts if ctx["name"] == context), None)
        else:
            target_context = active_context
        if not target_context:
            return None

        loader = config.kube_config._get_kube_config_loader(
            filename=kubeconfig_path, active_context=target_context["name"]
        )
        loader.load_and_set(Configuration())

        user_name = target_context["context"]["user"]
        user_config = None
        for user in loader._config.safe_get("users") or []:
            if user.safe_get("name") == user_name:
                user_config = user.safe_get("user") or {}
                break

        if not user_config:
            return None

        token = None
        if "token" in user_config:
            token = user_config["token"]
        elif "tokenFile" in user_config:
            token_file_path = user_config["tokenFile"]
            with open(os.path.expanduser(token_file_path), "r") as f:
                token = f.read().strip()

        return token

    except Exception:
        # Silently return None if kubeconfig detection fails
        return None


def _cw_token_input_required() -> bool:
    """Determines if a cw_token is needed for authentication to the CoreWeave api.

    Determined needed if we are using PodIdentity with access to the /cks/clusters endpoint.
    Does not validate that all necessary permissions are bound to the user
    """
    uri = os.getenv("AWS_CONTAINER_CREDENTIALS_FULL_URI")
    token_file = os.getenv("AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE")
    cw_token = os.getenv("CW_TOKEN")
    kubeconfig = os.getenv("KUBECONFIG")

    token = ""
    if uri and token_file and os.path.exists(token_file):
        token = open(token_file).read()
    elif cw_token:
        token = cw_token
    elif os.getenv("KUBECONFIG") and os.path.exists(os.path.expanduser("~/.kube/config")):
        token = detect_cw_token()

    if token:
        try:
            response = requests.get(
                "http://metadata.coreweave.internal/cks/clusters",
                headers={"Authorization": f"Bearer {token}"},
                timeout=2,
            )
            if response.status_code == 200:
                return False
            else:
                return True
        except requests.RequestException:
            return True
    else:
        return True


def cw_token_input() -> tuple[mo.Html | None, mo.ui.form | None]:
    """Create a form for a user to input their CW_TOKEN secret for auth.

    To access the token in your code, use token_form.value.get("cw_token")
    """
    if not _cw_token_input_required():
        return None, None

    token_form = (
        mo.md("{cw_token}")
        .batch(cw_token=mo.ui.text(kind="password", placeholder="CW-SECRET-...", full_width=True))  # type: ignore
        .form(submit_button_label="Connect", bordered=False)
    )
    token_ui = mo.md(
        f"""
        /// admonition | Manual Initialization Required
            type: warning

        Automatic credentials not found. Please enter your [CoreWeave access token](https://console.coreweave.com/tokens) to initialize the ObjectStorage client.
        ///

        {token_form}
        """
    )
    return token_ui, token_form
