from datetime import timedelta
import numpy as np
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSlider, QGroupBox, QMessageBox,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from backend.controllers.propagator_controller import format_utc_time, parse_utc_time
from backend.utils.file_handler import TaskWorker, WorkerThread
from backend.utils.map_loader import MapLoader
from ui.dialogs.propagator_settings_dialog import PropagatorSettingsDialog


class PropagatorWidget(QWidget):
    is_ground_trace = False
    title_prefix = 'SGP4 Propagation'
    settings_dialog = PropagatorSettingsDialog

    def __init__(self, propagation_data, propagator_controller):
        super().__init__()
        self.propagation_data = dict(propagation_data)
        self.propagator_controller = propagator_controller
        self.trajectory = None
        self.current_index = 0
        self.is_playing = False
        self._worker = None
        self._disposed = False
        self._background = None
        self._saving = False
        self.settings = self._default_settings()
        self.world = MapLoader().get_world_map()
        self._setup_ui()
        self._setup_timer()

    def _default_settings(self):
        return {'trace_color': '#FFD700', 'marker_color': '#FF0000', 'thickness': 1}

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        layout.addWidget(self._create_time_controls())
        layout.addWidget(self._create_playback_controls())
        self.status_label = QLabel(MapLoader().error)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.figure = Figure(figsize=(14, 10), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.figure.savefig = self._custom_savefig
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        self._draw_world_map()
        self._create_trajectory_artists()
        self._draw_connection = self.canvas.mpl_connect('draw_event', self._cache_background)
        self.figure.tight_layout(pad=1.0)
        self.canvas.draw_idle()

    def _create_time_controls(self):
        group = QGroupBox('Time Configuration (UTC)')
        layout = QHBoxLayout(group)
        layout.addWidget(QLabel('Start:'))
        epoch = self.propagation_data['epoch']
        self.start_time_input = QLineEdit(format_utc_time(epoch))
        self.start_time_input.setReadOnly(not self.is_ground_trace)
        self.start_time_input.setMinimumWidth(200)
        layout.addWidget(self.start_time_input)
        layout.addWidget(QLabel('Stop:'))
        stop = format_utc_time(epoch + timedelta(days=1)) if self.is_ground_trace else '+5 days'
        self.stop_time_input = QLineEdit(stop)
        self.stop_time_input.setMinimumWidth(140)
        self.stop_time_input.setToolTip('YYYY-MM-DD HH:MM:SS in UTC' if self.is_ground_trace else 'An absolute UTC date/time or a duration such as +5 days')
        layout.addWidget(self.stop_time_input)
        self.compute_button = QPushButton('Compute')
        self.compute_button.clicked.connect(self._compute_trajectory)
        layout.addWidget(self.compute_button)
        layout.addWidget(QLabel('Current Time:'))
        if self.is_ground_trace:
            self.current_time_input = QLineEdit('--')
            self.current_time_input.setReadOnly(True)
            self.current_time_input.setMinimumWidth(200)
            self.current_time_input.returnPressed.connect(self._on_time_input_changed)
            layout.addWidget(self.current_time_input)
        else:
            self.current_time_label = QLabel('--')
            self.current_time_label.setMinimumWidth(180)
            layout.addWidget(self.current_time_label)
        return group

    def _create_playback_controls(self):
        group = QGroupBox('Playback Controls')
        layout = QHBoxLayout(group)
        self.play_button = QPushButton('▶ Play')
        self.play_button.clicked.connect(self._toggle_playback)
        self.play_button.setEnabled(False)
        layout.addWidget(self.play_button)
        layout.addWidget(QLabel('Step:'))
        self.step_slider = QSlider(Qt.Orientation.Horizontal)
        self.step_slider.setRange(1, 100)
        self.step_slider.setValue(10)
        self.step_slider.setMaximumWidth(150)
        self.step_slider.setEnabled(False)
        self.step_slider.setToolTip('Number of trajectory samples advanced per animation frame')
        layout.addWidget(self.step_slider)
        self.step_label = QLabel('10')
        self.step_label.setMinimumWidth(30)
        self.step_slider.valueChanged.connect(lambda value: self.step_label.setText(str(value)))
        layout.addWidget(self.step_label)
        self.reset_button = QPushButton('⟲ Reset')
        self.reset_button.clicked.connect(self._reset_animation)
        self.reset_button.setEnabled(False)
        layout.addWidget(self.reset_button)
        self.settings_button = QPushButton('⚙ Settings')
        self.settings_button.clicked.connect(self._open_settings)
        layout.addWidget(self.settings_button)
        layout.addStretch()
        return group

    def _setup_timer(self):
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._update_animation)

    def _draw_world_map(self):
        if self.world is not None:
            self.world.plot(ax=self.ax, color='#4a4a4a', edgecolor='black', linewidth=0.3, rasterized=True)
        self.ax.set_facecolor('#2c5f8d')
        self.ax.set_xlim(-180, 180)
        self.ax.set_ylim(-90, 90)
        self.ax.set_xticks(np.arange(-180, 181, 30))
        self.ax.set_yticks(np.arange(-90, 91, 30))
        self.ax.set_xlabel('Longitude (deg)')
        self.ax.set_ylabel('Latitude (deg)')
        self.ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        self.ax.set_title(f"{self.title_prefix}: {self.propagation_data['name']}")

    def _create_trajectory_artists(self):
        self.trajectory_line, = self.ax.plot([], [], color=self.settings['trace_color'],
                                             linewidth=self.settings['thickness'], alpha=0.6)
        self.satellite_marker, = self.ax.plot([], [], 'o', color=self.settings['marker_color'],
                                              markersize=10, animated=self.canvas.supports_blit)

    def _computation_request(self):
        data = self.propagation_data
        self.propagator_controller._parse_stop_time(data['epoch'], self.stop_time_input.text())
        return self.propagator_controller.compute_trajectory, (
            data['tle_line1'], data['tle_line2'], data['epoch'], self.stop_time_input.text(),
        )

    def _compute_trajectory(self):
        if self._disposed:
            return
        if self._worker is not None:
            self._worker.stop()
            self.compute_button.setEnabled(False)
            self.status_label.setText('Cancelling calculation...')
            return
        try:
            function, arguments = self._computation_request()
        except (ValueError, OverflowError) as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, 'Time Configuration', str(exc))
            return
        self.pause()
        self._worker = TaskWorker(function, *arguments, step_seconds=60)
        self._worker.result_ready.connect(self._computation_ready)
        self._worker.failed.connect(self._computation_failed)
        self._worker.finished.connect(self._computation_finished)
        self._set_busy(True)
        self.status_label.setText('Calculating trajectory...')
        self._worker.start()

    @Slot(object)
    def _computation_ready(self, result):
        if self._disposed or WorkerThread.shutting_down or self.sender() is not self._worker or self._worker.is_cancelled():
            return
        self.trajectory = result
        self.current_index = self._initial_index()
        self._draw_trajectory()
        self._update_marker()
        count = len(result['times'])
        message = f'{count:,} samples at 60-second intervals. Times are UTC.'
        failed = result.get('failed_samples', 0)
        if failed:
            message += f" {failed:,} failed samples were omitted: {'; '.join(result.get('errors', []))}"
        if MapLoader().error:
            message += f' {MapLoader().error}'
        self.status_label.setText(message)

    @Slot(str)
    def _computation_failed(self, message):
        if self._disposed or WorkerThread.shutting_down or self.sender() is not self._worker or self._worker.is_cancelled():
            return
        self.status_label.setText(message)
        QMessageBox.warning(self, 'Trajectory Calculation', message)

    @Slot()
    def _computation_finished(self):
        if self._disposed or self.sender() is not self._worker:
            return
        cancelled = self._worker.is_cancelled()
        self._worker = None
        self._set_busy(False)
        if cancelled:
            self.status_label.setText('Calculation cancelled.')

    def _set_busy(self, busy):
        self.compute_button.setText('Cancel' if busy else 'Compute')
        self.compute_button.setEnabled(True)
        self.start_time_input.setEnabled(not busy)
        self.stop_time_input.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        ready = self.trajectory is not None and not busy
        for widget in (self.play_button, self.step_slider, self.reset_button):
            widget.setEnabled(ready)
        if self.is_ground_trace:
            self.current_time_input.setReadOnly(not ready or self.is_playing)

    def _initial_index(self):
        return 0

    def _draw_trajectory(self):
        lons = np.asarray(self.trajectory['longitudes'])
        lats = np.asarray(self.trajectory['latitudes'])
        indices = np.asarray(self.trajectory.get('sample_indices', np.arange(len(lons))))
        breaks = np.flatnonzero((np.abs(np.diff(lons)) > 180) | (np.diff(indices) != 1)) + 1
        self.trajectory_line.set_data(np.insert(lons, breaks, np.nan), np.insert(lats, breaks, np.nan))
        self.trajectory_line.set_color(self.settings['trace_color'])
        self.trajectory_line.set_linewidth(self.settings['thickness'])
        self.satellite_marker.set_color(self.settings['marker_color'])
        self._background = None
        self.canvas.draw_idle()

    def _open_settings(self):
        dialog = self.settings_dialog(self.settings, self)
        try:
            if dialog.exec():
                self.settings = dialog.get_settings()
                self._apply_settings()
        finally:
            dialog.deleteLater()

    def _apply_settings(self):
        if self.trajectory is not None:
            self._draw_trajectory()
            self._update_marker()

    def pause(self):
        self.is_playing = False
        self.timer.stop()
        self.play_button.setText('▶ Play')
        if self.is_ground_trace:
            self.current_time_input.setReadOnly(self.trajectory is None or self._worker is not None)

    def _toggle_playback(self):
        if self.trajectory is None or self._worker is not None:
            return
        if self.is_playing:
            self.pause()
        else:
            self.is_playing = True
            self.play_button.setText('⏸ Pause')
            if self.is_ground_trace:
                self.current_time_input.setReadOnly(True)
            self.timer.start()

    def _reset_animation(self):
        if self.trajectory is not None:
            self.pause()
            self.current_index = self._initial_index()
            self._update_marker()

    def _update_time_display(self):
        if self.trajectory is None:
            return
        text = format_utc_time(self.trajectory['times'][self.current_index])
        widget = self.current_time_input if self.is_ground_trace else self.current_time_label
        widget.setText(text)
        widget.setToolTip(text + ' UTC')

    def _update_marker(self):
        if self.trajectory is None or self._disposed:
            return
        self.satellite_marker.set_data([self.trajectory['longitudes'][self.current_index]],
                                      [self.trajectory['latitudes'][self.current_index]])
        self._update_time_display()
        if self._background is not None and self.canvas.supports_blit:
            self.canvas.restore_region(self._background)
            self.ax.draw_artist(self.satellite_marker)
            self.canvas.blit(self.ax.bbox)
        else:
            self.canvas.draw_idle()

    def _update_animation(self):
        if self.trajectory is not None and self.is_playing and not self._disposed:
            self.current_index = (self.current_index + self.step_slider.value()) % len(self.trajectory['times'])
            self._update_marker()

    def _on_time_input_changed(self):
        if not self.is_ground_trace or self.trajectory is None or self.is_playing or self._worker is not None:
            return
        try:
            target = parse_utc_time(self.current_time_input.text())
            self.current_index = self.propagator_controller.find_time_index(self.trajectory['times'], target)
            self._update_marker()
        except ValueError as exc:
            self.status_label.setText(str(exc))
            self._update_time_display()

    def _cache_background(self, event):
        if self._disposed or self._saving or not self.canvas.supports_blit:
            return
        self._background = self.canvas.copy_from_bbox(self.ax.bbox)
        self.ax.draw_artist(self.satellite_marker)
        self.canvas.blit(self.ax.bbox)

    def _custom_savefig(self, *args, **kwargs):
        kwargs['dpi'] = 300
        self._saving = True
        self.satellite_marker.set_animated(False)
        try:
            return Figure.savefig(self.figure, *args, **kwargs)
        finally:
            self.satellite_marker.set_animated(self.canvas.supports_blit)
            self._saving = False
            self._background = None
            self.canvas.draw_idle()

    def set_satellite_name(self, name):
        self.propagation_data['name'] = name
        self.ax.set_title(f'{self.title_prefix}: {name}')
        self._background = None
        self.canvas.draw_idle()

    def cleanup(self):
        if self._disposed:
            return
        self._disposed = True
        self.pause()
        if self._worker is not None:
            self._worker.stop()
            self._worker = None
        self.canvas.mpl_disconnect(self._draw_connection)
        self.trajectory = None
        self._background = None
        self.figure.clear()

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def hideEvent(self, event):
        if hasattr(self, 'timer'):
            self.pause()
        super().hideEvent(event)


def create_propagator_widget(propagation_data, propagator_controller):
    return PropagatorWidget(propagation_data, propagator_controller)
