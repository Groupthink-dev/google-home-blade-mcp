"""Configuration, constants, device types, and exceptions for Google Home Blade MCP."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# SDM API constants
# ---------------------------------------------------------------------------

SDM_BASE_URL = "https://smartdevicemanagement.googleapis.com/v1"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SDM_SCOPE = "https://www.googleapis.com/auth/sdm.service"
PUBSUB_SCOPE = "https://www.googleapis.com/auth/pubsub"

# Device types
DEVICE_TYPE_THERMOSTAT = "sdm.devices.types.THERMOSTAT"
DEVICE_TYPE_CAMERA = "sdm.devices.types.CAMERA"
DEVICE_TYPE_DOORBELL = "sdm.devices.types.DOORBELL"
DEVICE_TYPE_DISPLAY = "sdm.devices.types.DISPLAY"

DEVICE_TYPE_LABELS: dict[str, str] = {
    DEVICE_TYPE_THERMOSTAT: "Thermostat",
    DEVICE_TYPE_CAMERA: "Camera",
    DEVICE_TYPE_DOORBELL: "Doorbell",
    DEVICE_TYPE_DISPLAY: "Display",
}

# Trait namespaces
TRAIT_PREFIX = "sdm.devices.traits."

# Rate limits (SDM sandbox)
MAX_COMMAND_QPM = 5  # per project, per user, per device


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class GoogleHomeConfig:
    """Runtime configuration parsed from environment variables."""

    client_id: str
    client_secret: str
    refresh_token: str
    project_id: str
    pubsub_subscription: str | None = None
    write_enabled: bool = False

    @classmethod
    def from_env(cls) -> GoogleHomeConfig:
        """Parse configuration from environment variables."""
        client_id = os.environ.get("GOOGLE_HOME_CLIENT_ID", "")
        client_secret = os.environ.get("GOOGLE_HOME_CLIENT_SECRET", "")
        refresh_token = os.environ.get("GOOGLE_HOME_REFRESH_TOKEN", "")
        project_id = os.environ.get("GOOGLE_HOME_PROJECT_ID", "")

        if not all([client_id, client_secret, refresh_token, project_id]):
            missing = []
            if not client_id:
                missing.append("GOOGLE_HOME_CLIENT_ID")
            if not client_secret:
                missing.append("GOOGLE_HOME_CLIENT_SECRET")
            if not refresh_token:
                missing.append("GOOGLE_HOME_REFRESH_TOKEN")
            if not project_id:
                missing.append("GOOGLE_HOME_PROJECT_ID")
            raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            project_id=project_id,
            pubsub_subscription=os.environ.get("GOOGLE_HOME_PUBSUB_SUBSCRIPTION"),
            write_enabled=os.environ.get("GOOGLE_HOME_WRITE_ENABLED", "false").lower() in ("true", "1", "yes"),
        )


# ---------------------------------------------------------------------------
# Write gate
# ---------------------------------------------------------------------------


def is_write_enabled() -> bool:
    """Check if write operations are enabled."""
    return os.environ.get("GOOGLE_HOME_WRITE_ENABLED", "false").lower() in ("true", "1", "yes")


def require_write() -> str | None:
    """Return error message if writes disabled, else None."""
    if not is_write_enabled():
        return "Error: Write operations disabled. Set GOOGLE_HOME_WRITE_ENABLED=true to enable device commands."
    return None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GoogleHomeError(Exception):
    """Base exception for Google Home operations."""

    def __init__(self, message: str) -> None:
        super().__init__(_scrub_credentials(message))


class AuthError(GoogleHomeError):
    """Authentication or authorization failure."""


class NotFoundError(GoogleHomeError):
    """Device, structure, or room not found."""


class RateLimitError(GoogleHomeError):
    """API rate limit exceeded."""


class CommandError(GoogleHomeError):
    """Device command execution failed."""


class ConfigError(GoogleHomeError):
    """Missing or invalid configuration."""


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

_ERROR_PATTERNS: list[tuple[str, type[GoogleHomeError]]] = [
    ("unauthorized", AuthError),
    ("unauthenticated", AuthError),
    ("invalid_grant", AuthError),
    ("forbidden", AuthError),
    ("not found", NotFoundError),
    ("not_found", NotFoundError),
    ("rate limit", RateLimitError),
    ("quota exceeded", RateLimitError),
    ("resource_exhausted", RateLimitError),
    ("command failed", CommandError),
    ("failed_precondition", CommandError),
]


def classify_error(message: str) -> GoogleHomeError:
    """Map raw error string to typed exception."""
    lower = message.lower()
    for pattern, exc_cls in _ERROR_PATTERNS:
        if pattern in lower:
            return exc_cls(message)
    return GoogleHomeError(message)


# ---------------------------------------------------------------------------
# Credential scrubbing
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"(access_token|refresh_token|client_secret|token)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-./]+",
    re.I,
)

_SCRUB_PATTERNS = [
    (_TOKEN_RE, r"\1=****"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-./]+", re.I), "Bearer ****"),
    (re.compile(r"ya29\.[A-Za-z0-9_\-]+"), "ya29.****"),
    (re.compile(r"1//[A-Za-z0-9_\-]+"), "1//****"),
]


def _scrub_credentials(text: str) -> str:
    """Remove OAuth tokens and secrets from error messages."""
    for pattern, replacement in _SCRUB_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Device model (lightweight, for internal use)
# ---------------------------------------------------------------------------


@dataclass
class DeviceInfo:
    """Parsed device from SDM API response."""

    name: str  # Full resource name: enterprises/{project}/devices/{id}
    device_type: str  # e.g. sdm.devices.types.THERMOSTAT
    traits: dict[str, dict[str, object]]  # trait_name -> trait_data
    parent_relations: list[dict[str, str]] = field(default_factory=list)

    @property
    def device_id(self) -> str:
        """Extract device ID from resource name."""
        return self.name.rsplit("/", 1)[-1]

    @property
    def type_label(self) -> str:
        """Human-readable device type."""
        return DEVICE_TYPE_LABELS.get(self.device_type, self.device_type.rsplit(".", 1)[-1])

    @property
    def custom_name(self) -> str:
        """Custom name from Info trait, or device ID."""
        info = self.traits.get(f"{TRAIT_PREFIX}Info", {})
        return str(info.get("customName", self.device_id))

    @property
    def room_name(self) -> str | None:
        """Room name from parent relations."""
        for rel in self.parent_relations:
            display = rel.get("displayName")
            if display:
                return str(display)
        return None

    @property
    def is_online(self) -> bool:
        """Check connectivity trait."""
        conn = self.traits.get(f"{TRAIT_PREFIX}Connectivity", {})
        return str(conn.get("status", "")).upper() == "ONLINE"

    @classmethod
    def from_api(cls, data: dict[str, object]) -> DeviceInfo:
        """Parse from SDM API device response."""
        return cls(
            name=str(data.get("name", "")),
            device_type=str(data.get("type", "")),
            traits=dict(data.get("traits", {})),  # type: ignore[arg-type]
            parent_relations=list(data.get("parentRelations", [])),  # type: ignore[arg-type]
        )


@dataclass
class StructureInfo:
    """Parsed structure from SDM API response."""

    name: str  # Full resource name
    display_name: str

    @property
    def structure_id(self) -> str:
        return self.name.rsplit("/", 1)[-1]

    @classmethod
    def from_api(cls, data: dict[str, object]) -> StructureInfo:
        traits = data.get("traits", {})
        info = traits.get(f"{TRAIT_PREFIX}Info", {}) if isinstance(traits, dict) else {}  # type: ignore[union-attr]
        return cls(
            name=str(data.get("name", "")),
            display_name=str(info.get("customName", "")) if isinstance(info, dict) else "",
        )


@dataclass
class RoomInfo:
    """Parsed room from SDM API response."""

    name: str  # Full resource name
    display_name: str

    @property
    def room_id(self) -> str:
        return self.name.rsplit("/", 1)[-1]

    @classmethod
    def from_api(cls, data: dict[str, object]) -> RoomInfo:
        traits = data.get("traits", {})
        info = traits.get(f"{TRAIT_PREFIX}Info", {}) if isinstance(traits, dict) else {}  # type: ignore[union-attr]
        return cls(
            name=str(data.get("name", "")),
            display_name=str(info.get("customName", "")) if isinstance(info, dict) else "",
        )
