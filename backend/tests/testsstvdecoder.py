import pytest

from demodulators.sstvdecoder import SSTVDecoder, SSTVMode, resolve_forced_mode
from pipeline.config.decoderconfigservice import DecoderConfigService


def test_sstv_config_keeps_forced_mode():
    config = DecoderConfigService().get_config(
        decoder_type="sstv", overrides={"sstv_mode": "scottie_s2"}
    )

    assert config.sstv_mode == "scottie_s2"


def test_forced_mode_bypasses_vis_detection():
    decoder = SSTVDecoder.__new__(SSTVDecoder)
    decoder.forced_mode = SSTVMode.SCOTTIE_S2
    decoder._decode_vis = lambda _vis_start: pytest.fail("VIS detection should be bypassed")

    assert decoder._select_mode(123) is SSTVMode.SCOTTIE_S2


def test_auto_mode_uses_vis_detection():
    decoder = SSTVDecoder.__new__(SSTVDecoder)
    decoder.forced_mode = None
    decoder._decode_vis = lambda _vis_start: SSTVMode.ROBOT_36

    assert decoder._select_mode(123) is SSTVMode.ROBOT_36


def test_rejects_unknown_forced_mode():
    with pytest.raises(ValueError, match="Unsupported forced SSTV mode"):
        resolve_forced_mode("pd120")
