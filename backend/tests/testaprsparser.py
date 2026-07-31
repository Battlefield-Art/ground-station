"""Tests for APRS information-field parsing and AX.25 integration."""

from telemetry.aprsparser import APRSParser
from telemetry.parser import TelemetryParser


def _ax25_address(callsign: str, ssid: int = 0, final: bool = False) -> bytes:
    ssid_byte = 0x60 | ((ssid & 0x0F) << 1) | int(final)
    return bytes(ord(character) << 1 for character in callsign.ljust(6)) + bytes([ssid_byte])


def test_compressed_position_and_base91_telemetry_from_live_packet():
    parsed = APRSParser.parse(b"!L9y@)T<7Ca  GLoRa APRS|&:%X|")

    assert parsed["data_type"] == "position_without_timestamp"
    assert parsed["position"] == {
        "latitude": 40.601269,
        "longitude": 22.967211,
        "format": "compressed",
        "symbol_table": "L",
        "symbol_code": "a",
    }
    assert parsed["comment"] == "GLoRa APRS"
    assert parsed["telemetry"] == {
        "encoding": "base91",
        "sequence": 480,
        "channels": [419],
        "raw": "&:%X",
    }
    assert parsed["values"]["telemetry_channel_1_raw"] == 419


def test_uncompressed_position_extensions_are_normalized():
    parsed = APRSParser.parse(b"!4903.50N/07201.75W>088/036Test/A=001234")

    assert parsed["position"]["latitude"] == 49.058333
    assert parsed["position"]["longitude"] == -72.029167
    assert parsed["position"]["course_degrees"] == 88
    assert parsed["position"]["speed_knots"] == 36
    assert parsed["position"]["altitude_feet"] == 1234
    assert parsed["position"]["altitude_meters"] == 376.1


def test_classic_telemetry_and_message_packets():
    telemetry = APRSParser.parse(b"T#007,123,45.5,0,255,8,10101010,Beacon")
    message = APRSParser.parse(b":SV2AHT-10:hello from APRS{42")

    assert telemetry["telemetry"]["sequence"] == 7
    assert telemetry["telemetry"]["channels"] == [123, 45.5, 0, 255, 8]
    assert telemetry["telemetry"]["digital_bits"] == "10101010"
    assert message["message"] == {
        "addressee": "SV2AHT-10",
        "text": "hello from APRS",
        "id": "42",
    }


def test_telemetry_parser_selects_aprs_semantics_from_framing_hint():
    packet = (
        _ax25_address("APLRG1")
        + _ax25_address("SV2AHT", ssid=10, final=True)
        + b"\x03\xf0"
        + b"!L9y@)T<7Ca  GLoRa APRS|&:%X|"
    )

    parsed = TelemetryParser().parse(
        packet,
        protocol_hint="ax25",
        parser_hint={"framing": "aprs"},
    )

    assert parsed["success"] is True
    assert parsed["parser"] == "ax25+aprs"
    assert parsed["frame"]["source"] == "SV2AHT-10"
    assert parsed["telemetry"]["format"] == "aprs"
    assert parsed["telemetry"]["position"]["latitude"] == 40.601269
