"""Server settings from environment variables (no config files, no secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: Path = REPO_ROOT / "data"
    reports_dir: Path = REPO_ROOT / "reports"
    static_dir: Path | None = REPO_ROOT / "frontend" / "dist"
    enable_sim: bool = True
    log_level: str = "INFO"
    queue_size: int = 2048
    reconnect_backoff_s: tuple[float, ...] = field(default=(0.2, 0.5, 1.0))
    seed: int | None = None

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"

    @property
    def datasets_dir(self) -> Path:
        return self.data_dir / "datasets"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @classmethod
    def from_env(cls) -> Settings:
        static = os.environ.get("BRAINOS_STATIC_DIR")
        return cls(
            host=os.environ.get("BRAINOS_HOST", cls.host),
            port=int(os.environ.get("BRAINOS_PORT", cls.port)),
            data_dir=Path(os.environ.get("BRAINOS_DATA_DIR", str(REPO_ROOT / "data"))),
            reports_dir=Path(os.environ.get("BRAINOS_REPORTS_DIR", str(REPO_ROOT / "reports"))),
            static_dir=Path(static) if static else REPO_ROOT / "frontend" / "dist",
            enable_sim=_flag("BRAINOS_ENABLE_SIM", True),
            log_level=os.environ.get("BRAINOS_LOG_LEVEL", "INFO").upper(),
        )
