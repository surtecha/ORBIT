import re
import uuid
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QFileDialog
from backend.tle.parser import parse_tle_file, parse_tle_text
from backend.utils.file_handler import TaskWorker, WorkerThread
from data.satellite import SatelliteData


class TLEController(QObject):
    satellite_added = Signal(object)
    satellite_renamed = Signal(str, str)
    satellite_removed = Signal(str)
    satellite_data_ready = Signal(str, str, object)
    satellite_plot_ready = Signal(str, str, object)
    operation_failed = Signal(str, str)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.satellites = {}
        self.worker = None

    def load_tle(self, filepath):
        self._start_import(parse_tle_file, filepath, split_objects=True)

    def load_spacetrack_tle(self, tle_data):
        self._start_import(parse_tle_text, tle_data)

    def _start_import(self, function, *args, **kwargs):
        if self.worker is not None or WorkerThread.shutting_down:
            return
        self.worker = TaskWorker(function, *args, **kwargs)
        self.worker.result_ready.connect(self._import_ready)
        self.worker.failed.connect(self._import_failed)
        self.worker.finished.connect(self._import_finished)
        self.busy_changed.emit(True)
        self.worker.start()

    @Slot(object)
    def _import_ready(self, results):
        if WorkerThread.shutting_down or self.sender() is not self.worker or self.worker.is_cancelled():
            return
        try:
            satellites = [SatelliteData(
                satellite_id=str(uuid.uuid4()), norad_id=result['norad_id'],
                name=result.get('name', result['norad_id']),
                dataframe=result['dataframe'], tle_lines=result['tle_lines'],
            ) for result in results]
        except Exception as exc:
            self.operation_failed.emit('TLE Import', str(exc))
            return
        for satellite in satellites:
            self.satellites[satellite.satellite_id] = satellite
            self.satellite_added.emit(satellite)

    @Slot(str)
    def _import_failed(self, message):
        if not WorkerThread.shutting_down and self.sender() is self.worker:
            self.operation_failed.emit('TLE Import', message)

    @Slot()
    def _import_finished(self):
        if self.sender() is self.worker:
            self.worker = None
            self.busy_changed.emit(False)

    def rename_satellite(self, satellite_id, new_name):
        satellite = self.satellites.get(satellite_id)
        new_name = str(new_name).strip()
        if satellite is not None and new_name:
            satellite.name = new_name
            self.satellite_renamed.emit(satellite_id, new_name)

    def delete_satellite(self, satellite_id):
        if self.satellites.pop(satellite_id, None) is not None:
            self.satellite_removed.emit(satellite_id)

    def get_satellite_data(self, satellite_id):
        satellite = self.satellites.get(satellite_id)
        if satellite is not None:
            self.satellite_data_ready.emit(satellite_id, satellite.name, satellite.dataframe)

    def get_satellite_plot_data(self, satellite_id):
        satellite = self.satellites.get(satellite_id)
        if satellite is not None:
            self.satellite_plot_ready.emit(satellite_id, satellite.name, satellite.dataframe)

    @staticmethod
    def _filename(satellite):
        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', satellite.name).strip(' .')
        return name or satellite.norad_id

    def export_csv(self, satellite_id):
        satellite = self.satellites.get(satellite_id)
        if satellite is None:
            return
        filepath, _ = QFileDialog.getSaveFileName(None, 'Export as CSV',
                                                 f'{self._filename(satellite)}.csv', 'CSV Files (*.csv)')
        if filepath:
            try:
                satellite.dataframe.to_csv(filepath, index=False)
            except (OSError, ValueError) as exc:
                self.operation_failed.emit('CSV Export', str(exc))

    def export_tle(self, satellite_id, extension):
        satellite = self.satellites.get(satellite_id)
        if satellite is None:
            return
        if extension not in ('.tle', '.txt'):
            self.operation_failed.emit('TLE Export', 'Choose .tle or .txt.')
            return
        filepath, _ = QFileDialog.getSaveFileName(None, f'Export as TLE ({extension})',
                                                 self._filename(satellite) + extension,
                                                 f'TLE Files (*{extension})')
        if filepath:
            try:
                text = ''.join(f'{line1}\n{line2}\n' for line1, line2 in satellite.tle_lines)
                Path(filepath).write_text(text, encoding='utf-8')
            except OSError as exc:
                self.operation_failed.emit('TLE Export', str(exc))

    def shutdown(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker = None
