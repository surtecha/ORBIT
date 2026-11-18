import math
from bisect import bisect_left
from datetime import timedelta
from PySide6.QtCore import QObject, Signal
from backend.controllers.propagator_controller import parse_utc_time
from backend.propagator.sgp4_propagator import as_utc, get_orbital_period_minutes
from backend.propagator.coordinate_converter import geographic_trajectory


class GroundTraceController(QObject):
    ground_trace_data_ready = Signal(str, str, object)
    operation_failed = Signal(str, str)

    def __init__(self, tle_controller):
        super().__init__()
        self.tle_controller = tle_controller

    def initiate_ground_trace(self, satellite_id):
        satellite = self.tle_controller.satellites.get(satellite_id)
        if satellite is None:
            return
        try:
            line1, line2, epoch = satellite.latest_record
            data = {'tle_line1': line1, 'tle_line2': line2, 'epoch': epoch,
                    'satellite_id': satellite_id, 'name': satellite.name,
                    'period_minutes': get_orbital_period_minutes(line1, line2)}
            self.ground_trace_data_ready.emit(satellite_id, satellite.name, data)
        except (ValueError, IndexError) as exc:
            self.operation_failed.emit('Ground Trace', str(exc))

    def compute_ground_trace(self, tle_line1, tle_line2, start_time, stop_time,
                             interval1_minutes, interval2_minutes, step_seconds=60, cancelled=None):
        start_time, stop_time = as_utc(start_time), as_utc(stop_time)
        self._validate_intervals(interval1_minutes, interval2_minutes)
        result = geographic_trajectory(tle_line1, tle_line2, start_time, stop_time, step_seconds, cancelled)
        result['midpoint_time'] = start_time + (stop_time - start_time) / 2
        result['midpoint_index'] = self._find_closest_time_index(result['times'], result['midpoint_time'])
        return self.reclassify_trajectory(result, interval1_minutes, interval2_minutes)

    def _validate_intervals(self, interval1_minutes, interval2_minutes):
        for value in (interval1_minutes, interval2_minutes):
            if not math.isfinite(float(value)) or not 0 <= float(value) <= 525600:
                raise ValueError('Trace intervals must be between 0 and 525600 minutes.')

    def reclassify_trajectory(self, trajectory, interval1_minutes, interval2_minutes):
        self._validate_intervals(interval1_minutes, interval2_minutes)
        midpoint = trajectory['midpoint_time']
        before = midpoint - timedelta(minutes=float(interval1_minutes))
        after = midpoint + timedelta(minutes=float(interval2_minutes))
        trajectory['segments'] = self._categorize_segments(trajectory['times'], before, after)
        return trajectory

    def _categorize_segments(self, times, segment1_end, segment2_end):
        return [0 if time < segment1_end else 1 if time <= segment2_end else 2 for time in times]

    def _find_closest_time_index(self, times, target_time):
        if not len(times):
            raise ValueError('The trajectory contains no times.')
        target_time = as_utc(target_time)
        index = bisect_left(times, target_time)
        if index == 0:
            return 0
        if index == len(times):
            return len(times) - 1
        return index - 1 if target_time - times[index - 1] <= times[index] - target_time else index

    def parse_time_input(self, time_str):
        try:
            return parse_utc_time(time_str)
        except ValueError:
            return None

    def find_time_index(self, times, target_time):
        return self._find_closest_time_index(times, target_time)
