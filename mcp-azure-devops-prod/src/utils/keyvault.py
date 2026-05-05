"""
utils/keyvault.py — Fetch secrets from Azure Key Vault using Managed Identity.
No client_secret needed — uses DefaultAzureCredential (Managed Identity on AKS).
"""

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from utils.logger import setup_logger

logger = setup_logger("keyvault")


class KeyVaultManager:
    """Load secrets from Azure Key Vault at startup."""

    def __init__(self, vault_name: str):
        self.vault_url = f"https://{vault_name}.vault.azure.net"
        self.credential = DefaultAzureCredential()
        self.client = SecretClient(vault_url=self.vault_url, credential=self.credential)
        logger.info(f"Key Vault client initialized: {self.vault_url}")

    def get_secret(self, name: str, default: str = "") -> str:
        """Retrieve a secret from Key Vault. Returns default if not found."""
        try:
            secret = self.client.get_secret(name)
            logger.info(f"Secret '{name}' loaded from Key Vault")
            return secret.value
        except Exception as e:
            logger.warning(f"Could not load secret '{name}': {e}")
            return default

    def load_all_secrets(self) -> dict:
        """Load all required secrets and return as a dict."""
        secrets = {
            "github_token": self.get_secret("github-token"),
            "jira_api_token": self.get_secret("jira-api-token"),
            "app_insights_api_key": self.get_secret("app-insights-api-key"),
        }
        loaded = sum(1 for v in secrets.values() if v)
        logger.info(f"Loaded {loaded}/{len(secrets)} secrets from Key Vault")
        return secrets
