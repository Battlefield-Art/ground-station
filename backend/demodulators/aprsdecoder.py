"""Raw-IQ APRS decoder built on the gr-satellites Bell 202 receive chain."""

import argparse
import gc
import logging
import multiprocessing
import os
import queue
import time
import traceback
from enum import Enum
from types import SimpleNamespace
from typing import Any, Dict, Optional

import numpy as np
import psutil
from scipy import signal

try:
    import setproctitle

    HAS_SETPROCTITLE = True
except ImportError:
    HAS_SETPROCTITLE = False

# GNU Radio's mmap buffers avoid exhausting System V shared-memory segments
# when a fresh graph is created for each batch.
os.environ.setdefault("GR_BUFFER_TYPE", "vmcirc_mmap_tmpfile")

from gnuradio import blocks, gr  # noqa: E402
from satellites.components.deframers.ax25_deframer import ax25_deframer  # noqa: E402
from satellites.components.demodulators.afsk_demodulator import afsk_demodulator  # noqa: E402

from constants import FramingType  # noqa: E402
from demodulators.basedecoderprocess import BaseDecoderProcess  # noqa: E402
from telemetry.parser import TelemetryParser  # noqa: E402

logger = logging.getLogger("aprsdecoder")


class DecoderStatus(Enum):
    """Status values emitted to the decoder UI."""

    LISTENING = "listening"
    DECODING = "decoding"
    SLEEPING = "sleeping"
    ERROR = "error"


class APRSMessageHandler(gr.basic_block):
    """Convert AX.25 PDUs into the common decoder callback contract."""

    def __init__(self, callback):
        gr.basic_block.__init__(self, name="aprs_message_handler", in_sig=None, out_sig=None)
        self.callback = callback
        self.message_port_register_in(gr.pmt.intern("in"))
        self.set_msg_handler(gr.pmt.intern("in"), self.handle_msg)

    def handle_msg(self, message):
        """Extract a decoded frame, AX.25 callsigns, and compatibility flags."""
        try:
            packet_data = (
                gr.pmt.to_python(gr.pmt.cdr(message))
                if gr.pmt.is_pair(message)
                else gr.pmt.to_python(message)
            )
            if isinstance(packet_data, np.ndarray):
                packet_data = bytes(packet_data)
            if not isinstance(packet_data, bytes):
                logger.warning("Unexpected APRS packet type: %s", type(packet_data))
                return

            callsigns = self._parse_callsigns(packet_data)
            packet_with_flags = b"\x7e" + packet_data + b"\x7e"
            self.callback(packet_with_flags, callsigns)
        except Exception as error:
            logger.error("Error handling APRS message: %s", error)
            traceback.print_exc()

    @staticmethod
    def _parse_callsigns(packet_data: bytes) -> Optional[Dict[str, str]]:
        """Read the destination and source addresses from an AX.25 frame."""
        if len(packet_data) < 14:
            return None
        try:
            destination = "".join(
                chr((packet_data[index] >> 1) & 0x7F) for index in range(6)
            ).strip()
            destination_ssid = (packet_data[6] >> 1) & 0x0F
            source = "".join(
                chr((packet_data[index] >> 1) & 0x7F) for index in range(7, 13)
            ).strip()
            source_ssid = (packet_data[13] >> 1) & 0x0F
            if not destination or not source:
                return None
            return {
                "from": f"{source}-{source_ssid}",
                "to": f"{destination}-{destination_ssid}",
            }
        except (IndexError, TypeError, ValueError):
            return None


class APRSFlowgraph(gr.top_block):
    """Batch raw IQ through NBFM, Bell 202 AFSK, and unscrambled AX.25."""

    OVERLAP_SECONDS = 3.0

    def __init__(
        self,
        sample_rate,
        callback,
        status_callback=None,
        baudrate=1200,
        af_carrier=1700,
        deviation=500,
        fm_deviation=3000,
        batch_interval=5.0,
        use_agc=True,
        dc_block=True,
        clk_bw=0.06,
        clk_limit=0.004,
    ):
        super().__init__("APRS Decoder")
        self.sample_rate = float(sample_rate)
        self.callback = callback
        self.status_callback = status_callback
        self.baudrate = int(baudrate)
        self.af_carrier = int(af_carrier)
        self.deviation = int(deviation)
        self.fm_deviation = int(fm_deviation)
        self.batch_interval = float(batch_interval)
        self.use_agc = use_agc
        self.dc_block = dc_block
        self.clk_bw = clk_bw
        self.clk_limit = clk_limit

        self.sample_buffer = np.array([], dtype=np.complex64)
        self.sample_lock = multiprocessing.Lock()
        self._previous_batch_packets: set[bytes] = set()
        self._current_batch_packets: set[bytes] = set()

    def process_samples(self, samples, vfo_center=0, vfo_bandwidth=0):
        """Accumulate complex IQ and process a batch once the interval is full."""
        samples = np.asarray(samples, dtype=np.complex64)
        if not len(samples):
            return

        with self.sample_lock:
            self.sample_buffer = np.concatenate((self.sample_buffer, samples))
            buffer_size = len(self.sample_buffer)
            should_process = buffer_size >= int(self.sample_rate * self.batch_interval)

        if should_process:
            if self.status_callback:
                self.status_callback(DecoderStatus.DECODING, {"buffer_samples": buffer_size})
            self._process_buffer(vfo_center, vfo_bandwidth, retain_overlap=True)

    def _process_buffer(self, vfo_center=0, vfo_bandwidth=0, retain_overlap=True):
        """Run one finite raw-IQ batch through a fresh GNU Radio graph."""
        with self.sample_lock:
            if not len(self.sample_buffer):
                return
            samples_to_process = self.sample_buffer.copy()
            overlap_samples = int(self.sample_rate * self.OVERLAP_SECONDS)
            if retain_overlap and len(self.sample_buffer) > overlap_samples:
                self.sample_buffer = self.sample_buffer[-overlap_samples:].copy()
            else:
                self.sample_buffer = np.array([], dtype=np.complex64)

        top_block = None
        self._current_batch_packets = set()
        try:
            top_block = gr.top_block("APRS Batch Processor")
            source = blocks.vector_source_c(samples_to_process.tolist(), repeat=False)
            options = argparse.Namespace(
                clk_bw=self.clk_bw,
                clk_limit=self.clk_limit,
                deviation=self.deviation,
                use_agc=self.use_agc,
                disable_dc_block=not self.dc_block,
                fm_deviation=self.fm_deviation,
            )
            demodulator = afsk_demodulator(
                baudrate=self.baudrate,
                samp_rate=self.sample_rate,
                iq=True,
                af_carrier=self.af_carrier,
                deviation=self.deviation,
                dump_path=None,
                options=options,
            )
            # Bell 202 APRS uses NRZI AX.25 without the G3RUH scrambler.
            deframer = ax25_deframer(g3ruh_scrambler=False, options=options)
            message_handler = APRSMessageHandler(self._on_packet)

            top_block.connect(source, demodulator, deframer)
            top_block.msg_connect((deframer, "out"), (message_handler, "in"))

            logger.info(
                "APRS batch: %d samples | %.0f sps | %d baud | tones=%d±%d Hz | "
                "FM deviation=%d Hz | VFO=%.0f Hz BW=%.0f Hz",
                len(samples_to_process),
                self.sample_rate,
                self.baudrate,
                self.af_carrier,
                abs(self.deviation),
                self.fm_deviation,
                vfo_center,
                vfo_bandwidth,
            )
            top_block.start()
            top_block.wait()
        except Exception as error:
            logger.error("Error processing APRS IQ batch: %s", error)
            traceback.print_exc()
        finally:
            # Only packets actually forwarded become overlap candidates. A packet
            # suppressed in this batch is therefore allowed again in the next one.
            self._previous_batch_packets = self._current_batch_packets
            if top_block is not None:
                try:
                    top_block.stop()
                    top_block.wait()
                    top_block.disconnect_all()
                except Exception:
                    pass
            if top_block is not None:
                del top_block
            gc.collect()
            time.sleep(0.1)

    def _on_packet(self, packet: bytes, callsigns: Optional[Dict[str, str]]) -> None:
        """Suppress only the adjacent-batch duplicate introduced by overlap."""
        if packet in self._previous_batch_packets:
            logger.debug("Suppressed duplicate APRS packet from batch overlap")
            return
        self._current_batch_packets.add(packet)
        self.callback(packet, callsigns)

    def flush_buffer(self, vfo_center=0, vfo_bandwidth=0):
        """Decode remaining IQ without retaining another overlap tail."""
        with self.sample_lock:
            has_samples = bool(len(self.sample_buffer))
        if has_samples:
            self._process_buffer(vfo_center, vfo_bandwidth, retain_overlap=False)


class APRSDecoder(BaseDecoderProcess):
    """Process-based APRS decoder that consumes SDR IQ broadcaster messages."""

    DECODER_TYPE = "aprs"
    INTERNAL_RF_BANDWIDTH = 12_500
    DEFAULT_FM_DEVIATION = 3_000
    TARGET_SAMPLE_RATE = 48_000

    def __init__(
        self,
        iq_queue,
        data_queue,
        session_id,
        config,
        output_dir="data/decoded",
        vfo=None,
        batch_interval=5.0,
        shm_monitor_interval=10,
        shm_restart_threshold=1000,
    ):
        super().__init__(
            iq_queue=iq_queue,
            data_queue=data_queue,
            session_id=session_id,
            config=config,
            output_dir=output_dir,
            vfo=vfo,
            shm_monitor_interval=shm_monitor_interval,
            shm_restart_threshold=shm_restart_threshold,
        )
        self.baudrate = int(config.baudrate or 1200)
        self.af_carrier = int(config.af_carrier or 1700)
        self.deviation = int(config.deviation or 500)
        self.fm_deviation = self.DEFAULT_FM_DEVIATION
        self.framing = FramingType.APRS
        self.config_source = config.config_source
        self.satellite = config.satellite or {}
        self.transmitter = config.transmitter or {}
        self.transmitter_description = self.transmitter.get("description") or "Unknown"
        self.transmitter_mode = self.transmitter.get("mode") or "AFSK"
        self.transmitter_downlink_freq = self.transmitter.get("downlink_low")
        self.batch_interval = float(batch_interval)

        self.sample_rate = None
        self.sdr_sample_rate = None
        self.sdr_center_freq = None
        self.decimation_factor = 1
        self.decimation_filter = None
        self.decimation_filter_state = None
        self.decimation_phase = 0
        self.translation_phase = 0.0
        self.flowgraph = None
        self.cached_vfo_state = None
        self.is_sleeping = False
        self.sleep_reason = None
        self.power_measurements = []
        self.max_power_history = 100
        self.current_power_dbfs = None

        if self.baudrate <= 0:
            raise ValueError(f"Invalid APRS baudrate: {self.baudrate}")
        os.makedirs(self.output_dir, exist_ok=True)

    def _get_decoder_type_for_init(self) -> str:
        return "APRS"

    def _get_decoder_type(self) -> str:
        return self.DECODER_TYPE

    def _get_vfo_state(self):
        return SimpleNamespace(**self.cached_vfo_state) if self.cached_vfo_state else None

    def _should_accept_packet(self, payload, callsigns):
        if not callsigns or not callsigns.get("from") or not callsigns.get("to"):
            logger.debug("APRS packet rejected because AX.25 callsigns are missing")
            return False
        return True

    def _get_decoder_specific_metadata(self):
        return {
            "af_carrier": self.af_carrier,
            "deviation": self.deviation,
            "fm_deviation": self.fm_deviation,
            "batch_interval": self.batch_interval,
        }

    def _get_decoder_config_metadata(self):
        return {
            "source": self.config_source,
            "framing": FramingType.APRS,
            "payload_protocol": "ax25",
        }

    def _get_payload_protocol(self):
        return "ax25"

    def _get_filename_params(self):
        return f"{self.baudrate}baud"

    def _get_parameters_string(self):
        return (
            f"{self.baudrate}baud Bell 202, {self.af_carrier}Hz carrier, "
            f"{abs(self.deviation)}Hz tone deviation"
        )

    def _get_demodulator_params_metadata(self):
        return {
            "input": "raw_iq",
            "af_carrier_hz": self.af_carrier,
            "tone_deviation_hz": self.deviation,
            "fm_deviation_hz": self.fm_deviation,
            "rf_bandwidth_hz": self.INTERNAL_RF_BANDWIDTH,
            "clock_recovery_bandwidth": 0.06,
            "clock_recovery_limit": 0.004,
        }

    @staticmethod
    def _is_vfo_in_sdr_bandwidth(vfo_center, sdr_center, sdr_sample_rate):
        offset = vfo_center - sdr_center
        usable_half_bandwidth = (sdr_sample_rate / 2) * 0.98
        return (
            abs(offset) <= usable_half_bandwidth,
            offset,
            usable_half_bandwidth - abs(offset),
        )

    def _frequency_translate(self, samples, offset_frequency, sample_rate):
        """Translate one IQ chunk while preserving oscillator phase."""
        if offset_frequency == 0:
            self.translation_phase = 0.0
            return samples
        angular_frequency = 2 * np.pi * offset_frequency / sample_rate
        phases = self.translation_phase + angular_frequency * np.arange(len(samples))
        self.translation_phase = float(
            (self.translation_phase + angular_frequency * len(samples)) % (2 * np.pi)
        )
        return samples * np.exp(-1j * phases)

    @staticmethod
    def _design_decimation_filter(bandwidth, sample_rate):
        transition = bandwidth * 0.1
        tap_count = min(1001, int(sample_rate / transition) | 1)
        return signal.firwin(tap_count, bandwidth / 2, fs=sample_rate)

    def _decimate_iq(self, samples):
        if self.decimation_factor == 1:
            return np.asarray(samples, dtype=np.complex64)

        # IQ arrives in independently queued chunks. Preserve both FIR history
        # and the global downsampling phase so chunk boundaries do not insert
        # timing slips into an AX.25 frame.
        assert self.decimation_filter is not None
        if self.decimation_filter_state is None:
            self.decimation_filter_state = np.zeros(
                len(self.decimation_filter) - 1, dtype=np.complex128
            )
        filtered, self.decimation_filter_state = signal.lfilter(
            self.decimation_filter,
            1,
            samples,
            zi=self.decimation_filter_state,
        )
        start = self.decimation_phase
        self.decimation_phase = (start - len(samples)) % self.decimation_factor
        return np.asarray(filtered[start :: self.decimation_factor], dtype=np.complex64)

    def _initialize_dsp(self, sdr_rate, sdr_center, vfo_state):
        """Create decimation state and the raw-IQ APRS batch graph."""
        self.sdr_sample_rate = float(sdr_rate)
        self.sdr_center_freq = float(sdr_center)
        self.decimation_factor = max(1, int(self.sdr_sample_rate / self.TARGET_SAMPLE_RATE))
        self.sample_rate = self.sdr_sample_rate / self.decimation_factor
        self.decimation_filter = self._design_decimation_filter(
            self.INTERNAL_RF_BANDWIDTH, self.sdr_sample_rate
        )
        self.decimation_filter_state = None
        self.decimation_phase = 0
        self.translation_phase = 0.0
        self.flowgraph = APRSFlowgraph(
            sample_rate=self.sample_rate,
            callback=self._on_packet_decoded,
            status_callback=self._send_status_update,
            baudrate=self.baudrate,
            af_carrier=self.af_carrier,
            deviation=self.deviation,
            fm_deviation=self.fm_deviation,
            batch_interval=self.batch_interval,
        )
        logger.info(
            "APRS decoder started: session=%s VFO=%s | %d baud Bell 202 | "
            "SDR=%.3f MHz @ %.2f MS/s | VFO=%.3f MHz | decode=%.0f S/s dec=%d",
            self.session_id,
            self.vfo,
            self.baudrate,
            self.sdr_center_freq / 1e6,
            self.sdr_sample_rate / 1e6,
            vfo_state.get("center_freq", 0) / 1e6,
            self.sample_rate,
            self.decimation_factor,
        )

    def _status_info(self, extra=None):
        info = {
            "baudrate": self.baudrate,
            "af_carrier_hz": self.af_carrier,
            "deviation_hz": self.deviation,
            "fm_deviation_hz": self.fm_deviation,
            "framing": FramingType.APRS,
            "rf_bandwidth_hz": self.INTERNAL_RF_BANDWIDTH,
            "input": "raw_iq",
        }
        info.update(self._get_power_statistics())
        if extra:
            info.update(extra)
        return info

    def _send_status_update(self, status, info=None):
        message = {
            "type": "decoder-status",
            "status": status.value,
            "decoder_type": self.DECODER_TYPE,
            "decoder_id": self.decoder_id,
            "session_id": self.session_id,
            "vfo": self.vfo,
            "timestamp": time.time(),
            "info": self._status_info(info),
        }
        try:
            self.data_queue.put(message, block=False)
            with self.stats_lock:
                self.stats["data_messages_out"] += 1
        except queue.Full:
            logger.warning("Data queue full, dropping APRS status update")

    def _send_stats_update(self, ingest_samples_per_second=0.0, ingest_chunks_per_second=0.0):
        with self.stats_lock:
            self.stats["ingest_samples_per_sec"] = ingest_samples_per_second
            self.stats["ingest_chunks_per_sec"] = ingest_chunks_per_second
            performance_stats = self.stats.copy()
        ui_stats = {
            "packets_decoded": self.packet_count,
            "baudrate": self.baudrate,
            "af_carrier": self.af_carrier,
            "deviation": self.deviation,
            "is_sleeping": self.is_sleeping,
            "ingest_samples_per_sec": round(ingest_samples_per_second, 1),
            "ingest_chunks_per_sec": round(ingest_chunks_per_second, 2),
        }
        ui_stats.update(self._get_power_statistics())
        try:
            self.data_queue.put(
                {
                    "type": "decoder-stats",
                    "decoder_type": self.DECODER_TYPE,
                    "session_id": self.session_id,
                    "vfo": self.vfo,
                    "timestamp": time.time(),
                    "stats": ui_stats,
                    "perf_stats": performance_stats,
                },
                block=False,
            )
            with self.stats_lock:
                self.stats["data_messages_out"] += 1
        except queue.Full:
            pass

    def run(self):
        """Consume IQ broadcaster messages until the process is stopped."""
        if HAS_SETPROCTITLE:
            setproctitle.setproctitle(f"Ground Station - APRS Decoder (VFO {self.vfo})")

        self.telemetry_parser = TelemetryParser()
        self.stats: Dict[str, Any] = {
            "iq_chunks_in": 0,
            "samples_in": 0,
            "samples_dropped_out_of_band": 0,
            "data_messages_out": 0,
            "queue_timeouts": 0,
            "packets_decoded": 0,
            "last_activity": None,
            "errors": 0,
            "cpu_percent": 0.0,
            "memory_mb": 0.0,
            "memory_percent": 0.0,
            "ingest_samples_per_sec": 0.0,
            "ingest_chunks_per_sec": 0.0,
        }
        self._send_status_update(DecoderStatus.LISTENING)

        process = psutil.Process()
        last_resource_time = time.time()
        last_stats_time = time.time()
        ingest_window_start = time.time()
        ingest_samples = 0
        ingest_chunks = 0
        chunks_processed = 0

        try:
            while self.running.value == 1:
                try:
                    iq_message = self.iq_queue.get(timeout=0.2)
                except queue.Empty:
                    with self.stats_lock:
                        self.stats["queue_timeouts"] += 1
                    iq_message = None

                if iq_message is not None:
                    samples = iq_message.get("samples")
                    sdr_center = iq_message.get(
                        "logical_center_freq_hz", iq_message.get("center_freq")
                    )
                    sdr_rate = iq_message.get("sample_rate")
                    vfo_state = iq_message.get("vfo_states", {}).get(self.vfo)
                    if samples is not None and len(samples):
                        with self.stats_lock:
                            self.stats["iq_chunks_in"] += 1
                            self.stats["samples_in"] += len(samples)
                            self.stats["last_activity"] = time.time()
                        ingest_samples += len(samples)
                        ingest_chunks += 1

                    if (
                        samples is not None
                        and len(samples)
                        and sdr_center is not None
                        and sdr_rate
                        and vfo_state
                        and vfo_state.get("active")
                    ):
                        self.cached_vfo_state = vfo_state
                        vfo_center = vfo_state.get("center_freq", 0)
                        vfo_bandwidth = vfo_state.get("bandwidth", self.INTERNAL_RF_BANDWIDTH)
                        in_band, offset, margin = self._is_vfo_in_sdr_bandwidth(
                            vfo_center, sdr_center, sdr_rate
                        )
                        if not in_band:
                            with self.stats_lock:
                                self.stats["samples_dropped_out_of_band"] += len(samples)
                            if not self.is_sleeping:
                                self.is_sleeping = True
                                self.sleep_reason = "vfo_out_of_sdr_bandwidth"
                                self._send_status_update(
                                    DecoderStatus.SLEEPING,
                                    {
                                        "reason": self.sleep_reason,
                                        "vfo_offset_hz": offset,
                                        "margin_hz": margin,
                                    },
                                )
                        else:
                            if self.is_sleeping:
                                self.is_sleeping = False
                                self.sleep_reason = None
                                self._send_status_update(
                                    DecoderStatus.DECODING,
                                    {"resumed_from_sleep": True},
                                )
                            if self.flowgraph is None:
                                self._initialize_dsp(sdr_rate, sdr_center, vfo_state)

                            translated = self._frequency_translate(
                                samples, vfo_center - sdr_center, sdr_rate
                            )
                            self._update_power_measurement(self._measure_signal_power(translated))
                            decimated = self._decimate_iq(translated)
                            assert self.flowgraph is not None
                            self.flowgraph.process_samples(decimated, vfo_center, vfo_bandwidth)
                            chunks_processed += 1
                            if chunks_processed % 50 == 0:
                                self._send_status_update(
                                    DecoderStatus.DECODING,
                                    {"packets_decoded": self.packet_count},
                                )
                            if chunks_processed % 100 == 0:
                                self._monitor_shared_memory()

                now = time.time()
                if now - last_resource_time >= 2.0:
                    memory = process.memory_info()
                    with self.stats_lock:
                        self.stats["cpu_percent"] = process.cpu_percent()
                        self.stats["memory_mb"] = memory.rss / (1024 * 1024)
                        self.stats["memory_percent"] = process.memory_percent()
                    last_resource_time = now
                if now - last_stats_time >= 1.0:
                    elapsed = max(now - ingest_window_start, 1e-9)
                    self._send_stats_update(
                        ingest_samples / elapsed,
                        ingest_chunks / elapsed,
                    )
                    ingest_window_start = now
                    ingest_samples = 0
                    ingest_chunks = 0
                    last_stats_time = now
        except KeyboardInterrupt:
            pass
        except Exception as error:
            logger.exception("APRS decoder error: %s", error)
            with self.stats_lock:
                self.stats["errors"] += 1
            self._send_status_update(DecoderStatus.ERROR, {"error": str(error)})
        finally:
            if self.flowgraph:
                vfo_state = self.cached_vfo_state or {}
                self.flowgraph.flush_buffer(
                    vfo_state.get("center_freq", 0),
                    vfo_state.get("bandwidth", 0),
                )

        final_status = "restart_requested" if self.should_restart() else "closed"
        try:
            self.data_queue.put(
                {
                    "type": "decoder-status",
                    "status": final_status,
                    "decoder_type": self.DECODER_TYPE,
                    "decoder_id": self.decoder_id,
                    "session_id": self.session_id,
                    "vfo": self.vfo,
                    "timestamp": time.time(),
                    "shm_segments": self.get_shm_segment_count(),
                    "restart_requested": self.should_restart(),
                },
                block=False,
            )
        except queue.Full:
            pass


__all__ = ["DecoderStatus", "APRSMessageHandler", "APRSFlowgraph", "APRSDecoder"]
