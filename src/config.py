import yaml
from pathlib import Path

# Load config file
config_path = Path(__file__).parent.parent / "config" / "config.yaml"
with open(config_path, "r", encoding="utf-8") as f:
    _config = yaml.safe_load(f)


def _to_bool(value, default=False):
    """Convert common config values to bool safely."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default

# Email config
EMAIL_PROVIDER = _config["email"].get("provider", "chatgpt")
EMAIL_WORKER_URL = _config["email"]["worker_url"]
EMAIL_DOMAIN = _config["email"]["domain"]
EMAIL_PREFIX_LENGTH = _config["email"]["prefix_length"]
EMAIL_WAIT_TIMEOUT = _config["email"]["wait_timeout"]
EMAIL_POLL_INTERVAL = _config["email"]["poll_interval"]
EMAIL_ADMIN_PASSWORD = _config["email"].get("admin_password", "")
EMAIL_WORKER_AUTH_HEADER = _config["email"].get("worker_auth_header", "X-Admin-Password")

# Browser config
HEADLESS = _config["browser"]["headless"]
SLOW_MO = _config["browser"]["slow_mo"]
BROWSER_TYPE = _config["browser"].get("type", "chrome")  # chrome or edge
DRIVER_STRATEGY = _config["browser"].get("driver_strategy", "auto")  # auto, manager, system, local
USER_AGENT_MODE = _config["browser"].get("user_agent_mode", "auto")
INCOGNITO = _to_bool(_config["browser"].get("incognito", False), False)

# Region config
REGION_CURRENT = _config["region"]["current"]
DEVICE_TYPE = _config["region"].get("device_type", "desktop")
REGION_USE_PROXY = _config["region"].get("use_proxy", False)
REGION_PROXY_MODE = _config["region"].get("proxy_mode", "static")
REGION_PROXY_URL = _config["region"].get("proxy_url", "")
REGION_PROXY_API = _config["region"].get("proxy_api", {})
REGION_PROFILES = _config["region"]["profiles"]

# HTTP config
HTTP_TIMEOUT = _config["http"]["timeout"]

# External sync config
EXTERNAL_SYNC = _config.get("external_sync", {})
EXTERNAL_SYNC_ENABLED = EXTERNAL_SYNC.get("enabled", False)
EXTERNAL_SYNC_URL = str(EXTERNAL_SYNC.get("url", "")).strip()
EXTERNAL_SYNC_API_KEY = str(EXTERNAL_SYNC.get("api_key", "")).strip()
EXTERNAL_SYNC_TIMEOUT = EXTERNAL_SYNC.get("timeout", HTTP_TIMEOUT)
EXTERNAL_SYNC_DEBUG_LOG = EXTERNAL_SYNC.get("debug_log", False)
EXTERNAL_SYNC_ACCOUNT_OPTIONS = EXTERNAL_SYNC.get("account_options") or {}
