import re
from datetime import datetime, timedelta
from PySide6.QtCore import QObject, Signal
from backend.propagator.sgp4_propagator import as_utc
from backend.propagator.coordinate_converter import geographic_trajectory


def parse_utc_time(text):
    try:
        value = datetime.fromisoformat(str(text).strip().replace('Z', '+00:00'))
        return as_utc(value)
    except (TypeError, ValueError):
        raise ValueError('Use YYYY-MM-DD HH:MM:SS, optionally with fractional seconds or a UTC offset.') from None


def format_utc_time(value):
    value = as_utc(value)
    precision = 'microseconds' if value.microsecond else 'seconds'
    return value.replace(tzinfo=None).isoformat(sep=' ', timespec=precision)


class PropagatorController(QObject):
    propagation_data_ready = Signal(str, str, object)
    operation_failed = Signal(str, str)

    def __init__(self, tle_controller):
        super().__init__()
        self.tle_controller = tle_controller

    def propagate_satellite(self, satellite_id):
        satellite = self.tle_controller.satellites.get(satellite_id)
        if satellite is None:
            return
        try:
            line1, line2, epoch = satellite.latest_record
            data = {'tle_line1': line1, 'tle_line2': line2, 'epoch': epoch,
                    'satellite_id': satellite_id, 'name': satellite.name}
            self.propagation_data_ready.emit(satellite_id, satellite.name, data)
        except (ValueError, IndexError) as exc:
            self.operation_failed.emit('Propagation', str(exc))

    def compute_trajectory(self, tle_line1, tle_line2, start_time, stop_time_str, step_seconds=60, cancelled=None):
        start_time = as_utc(start_time)
        stop_time = self._parse_stop_time(start_time, stop_time_str)
        return geographic_trajectory(tle_line1, tle_line2, start_time, stop_time, step_seconds, cancelled)

    def _parse_stop_time(self, start_time, stop_time_str):
        if isinstance(stop_time_str, datetime):
            return as_utc(stop_time_str)
        text = str(stop_time_str).strip()
        match = re.fullmatch(r'\+\s*(\d+(?:\.\d+)?)\s*(days?|hours?|minutes?|seconds?)', text, re.IGNORECASE)
        if match:
            units = {'day': 86400, 'hour': 3600, 'minute': 60, 'second': 1}
            try:
                return as_utc(start_time) + timedelta(seconds=float(match[1]) * units[match[2].lower().rstrip('s')])
            except (OverflowError, ValueError):
                raise ValueError('The requested duration is too large.') from None
        return parse_utc_time(text)
