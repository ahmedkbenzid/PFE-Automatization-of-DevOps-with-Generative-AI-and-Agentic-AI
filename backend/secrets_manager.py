"""Secrets management for CI/CD pipeline execution."""

import re
from typing import Dict, Optional


class SecretsManager:
    """Manage secrets for CI/CD execution with validation and masking."""

    # Common Docker Hub aliases
    DOCKER_HUB_ALIASES = {
        "DOCKERHUB_USERNAME": "DOCKER_USERNAME",
        "DOCKERHUB_TOKEN": "DOCKER_PASSWORD",
        "DOCKERHUB_PASSWORD": "DOCKER_PASSWORD",
    }

    # Secret key pattern (alphanumeric + underscore)
    SECRET_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    # Common secret keys that tools look for
    COMMON_SECRETS = {
        "docker": [
            "DOCKER_USERNAME",
            "DOCKER_PASSWORD",
            "DOCKERHUB_USERNAME",
            "DOCKERHUB_TOKEN",
            "REGISTRY_URL",
        ],
        "github": [
            "GITHUB_TOKEN",
            "GITHUB_USERNAME",
            "GH_TOKEN",
        ],
        "aws": [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_REGION",
        ],
        "kubernetes": [
            "KUBECONFIG_BASE64",
            "K8S_API_URL",
            "K8S_TOKEN",
        ],
        "gitlab": [
            "GITLAB_TOKEN",
            "GITLAB_URL",
        ],
        "registry": [
            "REGISTRY_USERNAME",
            "REGISTRY_PASSWORD",
            "REGISTRY_URL",
        ],
        "sonarqube": [
            "SONAR_TOKEN",
            "SONAR_HOST_URL",
            "SONAR_PROJECT_KEY",
        ],
    }

    @staticmethod
    def validate_secrets(secrets: Dict[str, str]) -> tuple[bool, Optional[str]]:
        """
        Validate secrets format and values.

        Returns:
            (is_valid, error_message)
        """
        if not isinstance(secrets, dict):
            return False, "Secrets must be a dictionary"

        for key, value in secrets.items():
            if not isinstance(key, str) or not isinstance(value, str):
                return False, "All secret keys and values must be strings"

            if not SecretsManager.SECRET_KEY_PATTERN.match(key):
                return False, f"Invalid secret key format: {key}"

            if len(value) == 0:
                return False, f"Secret value for '{key}' cannot be empty"

            if len(value) > 10000:
                return False, f"Secret value for '{key}' is too long (max 10000 chars)"

        return True, None

    @staticmethod
    def sanitize_secrets(raw_secrets: Dict[str, str]) -> Dict[str, str]:
        """
        Sanitize and normalize secrets.

        - Remove invalid keys
        - Apply Docker Hub aliases
        - Return cleaned dictionary
        """
        if not isinstance(raw_secrets, dict):
            return {}

        cleaned: Dict[str, str] = {}

        for raw_key, raw_value in raw_secrets.items():
            key = str(raw_key).strip()
            value = str(raw_value)

            # Skip empty keys or values
            if not key or value == "":
                continue

            # Validate key format
            if not SecretsManager.SECRET_KEY_PATTERN.match(key):
                continue

            cleaned[key] = value

        # Apply Docker Hub aliases (bi-directional for UI + workflow compatibility)
        if "DOCKERHUB_USERNAME" in cleaned and "DOCKER_USERNAME" not in cleaned:
            cleaned["DOCKER_USERNAME"] = cleaned["DOCKERHUB_USERNAME"]
        if "DOCKER_USERNAME" in cleaned and "DOCKERHUB_USERNAME" not in cleaned:
            cleaned["DOCKERHUB_USERNAME"] = cleaned["DOCKER_USERNAME"]

        dockerhub_token = (
            cleaned.get("DOCKERHUB_TOKEN")
            or cleaned.get("DOCKERHUB_PASSWORD")
            or cleaned.get("DOCKER_PASSWORD")
        )
        if dockerhub_token:
            cleaned.setdefault("DOCKERHUB_TOKEN", dockerhub_token)
            cleaned.setdefault("DOCKERHUB_PASSWORD", dockerhub_token)
            cleaned.setdefault("DOCKER_PASSWORD", dockerhub_token)

        return cleaned

    @staticmethod
    def mask_secret_value(value: str, show_chars: int = 4) -> str:
        """
        Mask a secret value for logging.

        Example: "my-secret-token-12345" -> "my-s***5"
        """
        if len(value) <= show_chars * 2:
            return "*" * len(value)

        visible_start = value[:show_chars]
        visible_end = value[-show_chars:]
        return f"{visible_start}***{visible_end}"

    @staticmethod
    def mask_secrets_dict(secrets: Dict[str, str]) -> Dict[str, str]:
        """Create a masked copy of secrets for logging."""
        return {
            key: SecretsManager.mask_secret_value(value)
            for key, value in secrets.items()
        }

    @staticmethod
    def build_env_dict(
        base_env: Dict[str, str],
        secrets: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """
        Build environment dictionary for subprocess execution.

        Args:
            base_env: Base environment variables
            secrets: Additional secrets to include

        Returns:
            Complete environment dictionary
        """
        env = dict(base_env)

        if not secrets:
            return env

        # Sanitize and add secrets
        clean_secrets = SecretsManager.sanitize_secrets(secrets)
        env.update(clean_secrets)

        # Add ACT_ prefixed versions for GitHub Actions compatibility
        for key, value in clean_secrets.items():
            env[f"ACT_SECRET_{key}"] = value

        return env

    @staticmethod
    def extract_required_secrets(pipeline_config: Dict) -> Dict[str, str]:
        """
        Extract list of required secrets from pipeline config.

        Returns:
            Dictionary of secret_name -> description
        """
        required = {}

        # Check for secrets mentioned in stages
        if "stages" in pipeline_config:
            for stage_name in pipeline_config.get("stages", []):
                stage_config = pipeline_config.get(stage_name, {})
                if isinstance(stage_config, str):
                    # Check string for common secret references
                    for secret_type, secrets in SecretsManager.COMMON_SECRETS.items():
                        for secret in secrets:
                            if secret in stage_config:
                                required[secret] = f"Required by {stage_name} stage"

        return required

    @staticmethod
    def get_secret_input_ui(secret_type: str) -> Dict[str, str]:
        """
        Get UI configuration for a secret type.

        Returns:
            Dictionary with field_name -> placeholder/label
        """
        configs = {
            "docker": {
                "DOCKER_USERNAME": "Docker Hub username",
                "DOCKER_PASSWORD": "Docker Hub password or token",
                "REGISTRY_URL": "Docker registry URL (optional)",
            },
            "github": {
                "GITHUB_TOKEN": "GitHub personal access token",
                "GH_TOKEN": "GitHub CLI token (alternative)",
            },
            "aws": {
                "AWS_ACCESS_KEY_ID": "AWS access key",
                "AWS_SECRET_ACCESS_KEY": "AWS secret access key",
                "AWS_REGION": "AWS region (e.g., us-east-1)",
            },
            "kubernetes": {
                "KUBECONFIG_BASE64": "Base64 encoded kubeconfig",
                "K8S_API_URL": "Kubernetes API URL",
                "K8S_TOKEN": "Kubernetes service account token",
            },
            "sonarqube": {
                "SONAR_TOKEN": "SonarQube user token",
                "SONAR_HOST_URL": "SonarQube server URL",
                "SONAR_PROJECT_KEY": "SonarQube project key",
            },
        }

        return configs.get(secret_type, {})
