import numpy as np
from matplotlib.collections import LineCollection
from ui.tabs.propagator_tab import PropagatorWidget
from ui.dialogs.ground_trace_settings_dialog import GroundTraceSettingsDialog
from backend.controllers.propagator_controller import parse_utc_time


class GroundTraceWidget(PropagatorWidget):
    is_ground_trace = True
    title_prefix = 'Ground Trace'
    settings_dialog = GroundTraceSettingsDialog

    def __init__(self, ground_trace_data, ground_trace_controller):
        super().__init__(ground_trace_data, ground_trace_controller)
        self.ground_trace_controller = ground_trace_controller
        self.ground_trace_data = self.propagation_data

    def _default_settings(self):
        interval = min(525600, max(0, int(self.propagation_data['period_minutes'] / 2)))
        return {
            'interval1_minutes': interval, 'interval2_minutes': interval,
            'segment_colors': ['#FFD700', '#FF4444', '#FFD700'],
            'marker_color': '#FF0000', 'thickness': 1,
            'segment_visibility': [True, True, True],
        }

    def _create_trajectory_artists(self):
        self.trajectory_line = LineCollection([], linewidths=self.settings['thickness'], alpha=0.7)
        self.ax.add_collection(self.trajectory_line)
        self.satellite_marker, = self.ax.plot([], [], 'o', color=self.settings['marker_color'],
                                              markersize=10, animated=self.canvas.supports_blit)

    def _computation_request(self):
        data = self.propagation_data
        start = parse_utc_time(self.start_time_input.text())
        stop = parse_utc_time(self.stop_time_input.text())
        return self.ground_trace_controller.compute_ground_trace, (
            data['tle_line1'], data['tle_line2'], start, stop,
            self.settings['interval1_minutes'], self.settings['interval2_minutes'],
        )

    def _initial_index(self):
        return self.trajectory['midpoint_index']

    def _draw_trajectory(self):
        lons = np.asarray(self.trajectory['longitudes'])
        lats = np.asarray(self.trajectory['latitudes'])
        labels = np.asarray(self.trajectory['segments'], dtype=int)[:-1]
        indices = np.asarray(self.trajectory.get('sample_indices', np.arange(len(lons))))
        visibility = np.asarray(self.settings['segment_visibility'], dtype=bool)
        keep = (np.abs(np.diff(lons)) <= 180) & (np.diff(indices) == 1) & visibility[labels]
        points = np.column_stack((lons, lats))
        edges = np.stack((points[:-1], points[1:]), axis=1)
        colors = np.asarray(self.settings['segment_colors'])
        self.trajectory_line.set_segments(edges[keep])
        self.trajectory_line.set_color(colors[labels[keep]].tolist())
        self.trajectory_line.set_linewidth(self.settings['thickness'])
        self.satellite_marker.set_color(self.settings['marker_color'])
        self._background = None
        self.canvas.draw_idle()

    def _apply_settings(self):
        if self.trajectory is not None:
            self.ground_trace_controller.reclassify_trajectory(
                self.trajectory, self.settings['interval1_minutes'], self.settings['interval2_minutes'])
        super()._apply_settings()


def create_ground_trace_widget(ground_trace_data, ground_trace_controller):
    return GroundTraceWidget(ground_trace_data, ground_trace_controller)
