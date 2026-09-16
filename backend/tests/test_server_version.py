from datetime import datetime

from server.version import get_full_version_info, get_system_info


def test_get_full_version_info_includes_server_time_fields():
    info = get_full_version_info()

    assert "serverTimeEpochMs" in info
    assert "serverTimeIsoUtc" in info
    assert isinstance(info["serverTimeEpochMs"], int)
    assert isinstance(info["serverTimeIsoUtc"], str)

    parsed_iso = datetime.fromisoformat(info["serverTimeIsoUtc"])
    parsed_iso_epoch_ms = int(parsed_iso.timestamp() * 1000)

    # Allow small drift between independently generated values.
    assert abs(parsed_iso_epoch_ms - info["serverTimeEpochMs"]) < 5000


def test_get_system_info_includes_footer_host_details():
    info = get_system_info(nonblocking_cpu=True)

    assert isinstance(info["hostname"], str)
    assert isinstance(info["uptime_seconds"], int)
    assert info["uptime_seconds"] >= 0
    assert "pretty_name" in info["os"]
