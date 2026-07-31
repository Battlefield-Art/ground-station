from observations.tasks.decoderhandler import (
    DecoderHandler,
    VFOManager,
    decoder_registry,
    map_scheduler_decoder_parameters,
)


def test_maps_aprs_scheduler_parameters_to_decoder_overrides():
    parameters = {
        "aprs_baudrate": 1240,
        "aprs_af_carrier": 1810,
        "aprs_deviation": 565,
    }

    assert map_scheduler_decoder_parameters("aprs", parameters) == {
        "baudrate": 1240,
        "af_carrier": 1810,
        "deviation": 565,
    }


def test_preserves_false_values_and_accepts_normalized_parameters():
    parameters = {
        "bpsk_baudrate": 1200,
        "bpsk_differential": False,
        "framing": "ax25",
    }

    assert map_scheduler_decoder_parameters("bpsk", parameters) == {
        "baudrate": 1200,
        "differential": False,
        "framing": "ax25",
    }


def test_nests_scheduler_geoscan_frame_size():
    parameters = {
        "fsk_baudrate": 9600,
        "fsk_framing": "geoscan",
        "fsk_geoscan_frame_size": 74,
    }

    assert map_scheduler_decoder_parameters("fsk", parameters) == {
        "baudrate": 9600,
        "framing": "geoscan",
        "framing_params": {"frame_size": 74},
    }


def test_ignores_invalid_scheduler_parameter_containers():
    assert map_scheduler_decoder_parameters("aprs", None) == {}
    assert map_scheduler_decoder_parameters("aprs", []) == {}


async def test_scheduled_aprs_parameters_reach_process_manager(monkeypatch):
    captured_kwargs = {}

    class ProcessManagerStub:
        processes = {"sdr-1": {"data_queue": object()}}

        @staticmethod
        def start_decoder(**kwargs):
            captured_kwargs.update(kwargs)
            return True

    monkeypatch.setattr(decoder_registry, "get_decoder_class", lambda _decoder: object)
    monkeypatch.setattr(decoder_registry, "supports_transmitter_config", lambda _decoder: False)
    monkeypatch.setattr(VFOManager, "configure_internal_vfo", lambda _manager, **_kwargs: None)

    handler = DecoderHandler(ProcessManagerStub())
    success = await handler.start_decoder_task(
        observation_id="observation-1",
        session_id="session-1",
        sdr_id="sdr-1",
        sdr_config={"center_freq": 144_800_000},
        task_config={
            "decoder_type": "aprs",
            "parameters": {
                "aprs_baudrate": 1240,
                "aprs_af_carrier": 1810,
                "aprs_deviation": 565,
            },
        },
        vfo_number=1,
    )

    assert success is True
    assert captured_kwargs["decoder_param_overrides"] == {
        "baudrate": 1240,
        "af_carrier": 1810,
        "deviation": 565,
    }
