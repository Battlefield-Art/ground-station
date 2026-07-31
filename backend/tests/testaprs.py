from constants import FramingType, payload_protocol_from_framing
from pipeline.config.decoderconfigservice import DecoderConfigService


def test_aprs_metadata_selects_the_unscrambled_ax25_path():
    config = DecoderConfigService().get_config(
        decoder_type="aprs",
        transmitter={"mode": "AFSK", "description": "1200 baud APRS Bell 202"},
    )

    assert config.framing == FramingType.APRS
    assert config.baudrate == 1200
    assert config.af_carrier == 1700
    assert config.deviation == 500
    assert payload_protocol_from_framing(config.framing) == "ax25"


def test_known_satellite_config_cannot_override_dedicated_aprs_framing():
    config = DecoderConfigService().get_config(
        decoder_type="aprs",
        satellite={"norad_id": 55181, "name": "SS-1"},
        transmitter={
            "mode": "AFSK",
            "description": "APRS digipeater",
            "baud": 1200,
            "downlink_low": 145_825_000,
        },
    )

    assert config.config_source == "satellite_config"
    assert config.framing == FramingType.APRS
    assert config.af_carrier == 1700


def test_aprs_without_transmitter_metadata_uses_bell202_defaults():
    config = DecoderConfigService().get_config(decoder_type="aprs")

    assert config.baudrate == 1200
    assert config.framing == FramingType.APRS
    assert config.af_carrier == 1700
    assert config.deviation == 500


def test_aprs_ignores_malformed_transmitter_baud_metadata():
    config = DecoderConfigService().get_config(
        decoder_type="aprs",
        transmitter={"mode": "APRS", "baud": "-"},
    )

    assert config.baudrate == 1200
