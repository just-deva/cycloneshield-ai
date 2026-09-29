"""Runtime configuration and the tenant registry (state / country packs as data)."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .hazard.surge import Shelf
from .storms.model import Storm

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("CYCLONESHIELD_DATA_DIR", BACKEND_DIR / "data"))
TENANT_DIR = Path(__file__).resolve().parent / "tenants_data"

load_dotenv(BACKEND_DIR / ".env")


class Settings(BaseModel):
    gemini_api_key: str | None = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_model: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.7-flash"))
    gemini_fallbacks: list[str] = Field(default_factory=lambda: [
        m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash-lite").split(",") if m.strip()])
    gcp_project: str | None = Field(default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT"))
    ee_enabled: bool = Field(default_factory=lambda: os.getenv("EE_ENABLED", "auto").lower() != "false")
    telegram_bot_token: str | None = Field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str | None = Field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID"))
    telegram_webhook_secret: str = Field(default_factory=lambda: os.getenv("TELEGRAM_WEBHOOK_SECRET", "cycloneshield"))
    dispatch_webhook_url: str | None = Field(default_factory=lambda: os.getenv("DISPATCH_WEBHOOK_URL"))
    public_base_url: str | None = Field(default_factory=lambda: os.getenv("PUBLIC_BASE_URL"))
    state_dir: Path = Field(default_factory=lambda: Path(os.getenv("CYCLONESHIELD_STATE_DIR", DATA_DIR / "state")))


@lru_cache
def settings() -> Settings:
    return Settings()


class Focus(BaseModel):
    lat: float
    lon: float
    label: str


class Recipient(BaseModel):
    role: str
    label: str


class SectorCfg(BaseModel):
    id: str
    lat: float
    lon: float
    width_km: float
    depth_m: float
    k: float = 1.0
    note: str = ""

    def to_shelf(self) -> Shelf:
        return Shelf(self.id, self.lat, self.lon, self.width_km, self.depth_m, self.k, self.note)


class Tenant(BaseModel):
    id: str
    name: str
    country: str
    iso3: str
    admin_label: str
    lgd_district_code: str | None = None
    focus: Focus
    bbox: list[float] = Field(description="south, west, north, east")
    dem_zoom: int = 12
    languages: list[str]
    intensity_scale: str = "IMD"
    authority: dict
    recipients: list[Recipient]
    tide_default_m: float = 0.4
    utc_offset_hours: float = 5.5
    tz_label: str = "IST"
    sectors: list[SectorCfg]
    replay_storms: list[str]
    calibration: dict | None = None
    attribution: list[str] = Field(default_factory=list)

    @property
    def dir(self) -> Path:
        return DATA_DIR / "exposure" / self.id


@lru_cache
def tenants() -> dict[str, Tenant]:
    out: dict[str, Tenant] = {}
    for path in sorted(TENANT_DIR.glob("*.json")):
        t = Tenant.model_validate(json.loads(path.read_text(encoding="utf-8")))
        out[t.id] = t
    return out


def get_tenant(tenant_id: str) -> Tenant:
    try:
        return tenants()[tenant_id]
    except KeyError as exc:
        raise KeyError(f"unknown tenant '{tenant_id}'. Available: {', '.join(tenants())}") from exc


@lru_cache
def storm_index() -> list[dict]:
    path = DATA_DIR / "storms" / "index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


@lru_cache
def load_replay(storm_id: str) -> Storm:
    path = DATA_DIR / "storms" / f"{storm_id}.json"
    if not path.exists():
        raise KeyError(f"unknown replay storm '{storm_id}'")
    return Storm.model_validate(json.loads(path.read_text(encoding="utf-8")))
