"""Non-secret settings (D-20) and write-only API keys (D-13)."""

import copy
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from netgrip.boundary.events import utc_now_iso
from netgrip.store.db import Database

KeyName = Literal["model", "search"]
Tier = Literal["strong", "standard", "fast", "verifier"]
PresetName = Literal["economy", "balanced", "maximum"]
PageReuse = Literal["1d", "always_refetch"]
EffortName = Literal["Low", "Medium", "High"]

OPUS = "anthropic/claude-opus-5.5"
SONNET = "anthropic/claude-sonnet-5.5"
HAIKU = "anthropic/claude-haiku-5.5"
GPT = "openai/gpt-5.2"


def _effort(depth: int, nodes: int, sources: int, parallel: int, confirm: int) -> dict:
    return {
        "max_depth": depth,
        "max_nodes": nodes,
        "sources_per_node": sources,
        "parallel": parallel,
        "sources_to_confirm": confirm,
    }


def _model(id: str, price_in: float | None, price_out: float | None) -> dict:
    priced = price_in is not None
    return {
        "id": id,
        "price_in_per_m": price_in,
        "price_out_per_m": price_out,
        "price_source": "provider" if priced else None,
    }


# Starting values from docs/plans/00-overview.md "Default settings"; they match the Settings
# preview. To be tuned after real runs.
DEFAULT_SETTINGS: dict[str, Any] = {
    "effort": {
        "Low": _effort(2, 12, 4, 2, 1),
        "Medium": _effort(4, 40, 8, 4, 2),
        "High": _effort(6, 80, 12, 6, 3),
    },
    "default_effort": "Medium",
    "spending_limit_usd": 5.0,
    "retry_before_pause_seconds": 300,
    "page_reuse": "1d",
    "politeness_seconds": 2.0,
    "capacity": {"investigations": 5, "model_calls": 8, "searches": 4, "browser_pages": 6},
    "model_endpoint": "https://openrouter.ai/api/v1",
    "presets": {
        "economy": {"strong": SONNET, "standard": HAIKU, "fast": HAIKU, "verifier": GPT},
        "balanced": {"strong": OPUS, "standard": SONNET, "fast": HAIKU, "verifier": GPT},
        "maximum": {"strong": OPUS, "standard": OPUS, "fast": SONNET, "verifier": GPT},
    },
    "default_preset": "balanced",
    "models": [
        _model(OPUS, 15.0, 75.0),
        _model(SONNET, 3.0, 15.0),
        _model(HAIKU, 1.0, 5.0),
        _model(GPT, None, None),
    ],
    "excluded_domains": [],
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Effort(_Strict):
    max_depth: int = Field(gt=0)
    max_nodes: int = Field(gt=0)
    sources_per_node: int = Field(gt=0)
    parallel: int = Field(gt=0)
    sources_to_confirm: int = Field(gt=0)


class Capacity(_Strict):
    investigations: int = Field(gt=0)
    model_calls: int = Field(gt=0)
    searches: int = Field(gt=0)
    browser_pages: int = Field(gt=0)


class ModelPrice(_Strict):
    id: str = Field(min_length=1)
    price_in_per_m: float | None = Field(default=None, gt=0)
    price_out_per_m: float | None = Field(default=None, gt=0)
    price_source: str | None = None


class SettingsModel(_Strict):
    effort: dict[EffortName, Effort]
    default_effort: EffortName
    spending_limit_usd: float = Field(gt=0)
    retry_before_pause_seconds: int = Field(gt=0)
    page_reuse: PageReuse
    politeness_seconds: float = Field(gt=0)
    capacity: Capacity
    model_endpoint: str = Field(min_length=1)
    presets: dict[PresetName, dict[Tier, str]]
    default_preset: PresetName
    models: list[ModelPrice]
    excluded_domains: list[str]


def _merge(base: dict, partial: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in partial.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


async def _stored(db: Database) -> dict:
    return {
        r["key"]: json.loads(r["value"]) for r in await db.read("SELECT key, value FROM settings")
    }


async def get_settings(db: Database) -> SettingsModel:
    return SettingsModel.model_validate(_merge(DEFAULT_SETTINGS, await _stored(db)))


async def patch_settings(db: Database, partial: dict) -> SettingsModel:
    """Deep-merge `partial` (lists replace) and store it. Invalid input changes nothing."""
    merged = SettingsModel.model_validate(_merge(DEFAULT_SETTINGS, await _stored(db)))
    merged = SettingsModel.model_validate(_merge(merged.model_dump(mode="json"), partial))
    data = merged.model_dump(mode="json")
    async with db.tx() as tx:
        await tx.executemany(
            "INSERT INTO settings(key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [(k, json.dumps(data[k], ensure_ascii=False)) for k in partial],
        )
    return merged


# --- Keys: write-only. Never returned over the API, never in events or logs. ----------------


class KeyStatus(BaseModel):
    set: bool
    status: Literal["none", "set", "rejected"]
    checked_at: str | None = None
    message: str | None = None


def _check_name(name: str) -> None:
    if name not in ("model", "search"):
        raise ValueError(f"unknown key name {name!r}")


async def set_key(db: Database, name: KeyName, value: str) -> None:
    _check_name(name)
    if not value.strip():
        raise ValueError("key is empty")
    async with db.tx() as tx:
        await tx.execute(
            "INSERT INTO secrets(name, value, status, checked_at, message)"
            " VALUES (?, ?, 'set', NULL, NULL)"
            " ON CONFLICT(name) DO UPDATE SET value = excluded.value, status = 'set',"
            " checked_at = NULL, message = NULL",
            [name, value.strip()],
        )


async def get_key(db: Database, name: KeyName) -> str | None:
    """Engine-internal only."""
    _check_name(name)
    rows = await db.read("SELECT value FROM secrets WHERE name = ?", [name])
    return rows[0]["value"] if rows else None


async def key_status(db: Database, name: KeyName) -> KeyStatus:
    _check_name(name)
    rows = await db.read("SELECT status, checked_at, message FROM secrets WHERE name = ?", [name])
    if not rows:
        return KeyStatus(set=False, status="none")
    r = rows[0]
    return KeyStatus(set=True, status=r["status"], checked_at=r["checked_at"], message=r["message"])


async def mark_key(
    db: Database, name: KeyName, status: Literal["set", "rejected"], message: str | None
) -> None:
    _check_name(name)
    async with db.tx() as tx:
        await tx.execute(
            "UPDATE secrets SET status = ?, checked_at = ?, message = ? WHERE name = ?",
            [status, utc_now_iso(), message, name],
        )


# --- Per-investigation settings: chosen at creation, defaults from the global settings -------


class InvestigationSettings(_Strict):
    effort: EffortName | None = None
    preset: PresetName | None = None
    tiers: dict[Tier, str] | None = None
    excluded_domains: list[str] | None = None
    prefer: Literal["none", "primary"] | None = None
    page_reuse: PageReuse | None = None
    spending_limit_usd: float | None = Field(default=None, gt=0)


def resolve_investigation_settings(glob: SettingsModel, chosen: dict) -> dict:
    """Fill what the user did not choose from the global settings, and snapshot the effort
    budget, so an investigation is not changed by later edits to the global settings."""
    c = InvestigationSettings.model_validate(chosen)
    effort = c.effort or glob.default_effort
    preset = c.preset or glob.default_preset
    tiers = dict(glob.presets[preset]) | (c.tiers or {})
    return {
        "effort": effort,
        "effort_budget": glob.effort[effort].model_dump(),
        "preset": preset,
        "tiers": tiers,
        "excluded_domains": c.excluded_domains
        if c.excluded_domains is not None
        else list(glob.excluded_domains),
        "prefer": c.prefer or "none",
        "page_reuse": c.page_reuse or glob.page_reuse,
        "spending_limit_usd": c.spending_limit_usd or glob.spending_limit_usd,
    }
