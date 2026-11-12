import pytest

from netgrip import __main__ as entry
from netgrip.config import Config


async def test_health(app_client):
    r = await app_client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_refuses_non_loopback(tmp_path, monkeypatch, capsys):
    cfg = Config(data_dir=tmp_path, host="0.0.0.0")
    monkeypatch.setattr(Config, "from_env", classmethod(lambda cls: cfg))
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code != 0
    assert "loopback" in capsys.readouterr().err
