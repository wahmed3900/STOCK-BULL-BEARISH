import os
from typing import Optional

try:
    from google.cloud import secretmanager
except ImportError:  # pragma: no cover - optional dependency
    secretmanager = None


def get_secret(secret_id: str, project_id: Optional[str] = None) -> Optional[str]:
    """Read a secret from Google Secret Manager."""
    project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise ValueError("Project ID not found. Set GOOGLE_CLOUD_PROJECT environment variable.")

    if secretmanager is None:
        raise ImportError("google-cloud-secret-manager is not installed")

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"

    try:
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as exc:
        print(f"Error accessing secret {secret_id}: {exc}")
        return None


def get_api_key(service_name: str, project_id: Optional[str] = None) -> Optional[str]:
    """Resolve a known service API key from Secret Manager."""
    secret_map = {
        "alpha_vantage": "alpha-vantage-key",
        "polygon": "polygon-api-key",
        "finnhub": "finnhub-key",
        "docker": "docker-hub-password",
    }

    secret_id = secret_map.get(service_name)
    if not secret_id:
        raise ValueError(f"No secret configured for {service_name}")

    return get_secret(secret_id, project_id=project_id)
