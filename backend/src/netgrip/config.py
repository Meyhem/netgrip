import os
from dataclasses import dataclass
from pathlib import Path

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class Config:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8321
    fake: bool = False
    fake_delay_ms: int = 0  # fake mode only: each fake model call takes this long
    fake_scenario: str = (
        "great_wall"  # fake mode only: the scripted model (adapters/fake_scenarios)
    )

    @classmethod
    def from_env(cls) -> "Config":
        data_dir = Path(os.environ.get("NETGRIP_DATA_DIR", "~/netgrip/data")).expanduser()
        port = int(os.environ.get("NETGRIP_PORT", "8321"))
        fake = os.environ.get("NETGRIP_FAKE", "").lower() in {"1", "true", "yes"}
        delay = int(os.environ.get("NETGRIP_FAKE_DELAY_MS", "0") or 0)
        scenario = os.environ.get("NETGRIP_FAKE_SCENARIO", "great_wall") or "great_wall"
        return cls(
            data_dir=data_dir, port=port, fake=fake, fake_delay_ms=delay, fake_scenario=scenario
        )

    @property
    def is_loopback(self) -> bool:
        return self.host in LOOPBACK_HOSTS

    @property
    def db_path(self) -> Path:
        return self.data_dir / "netgrip.sqlite"
