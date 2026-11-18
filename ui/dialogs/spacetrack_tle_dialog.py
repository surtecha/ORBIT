from datetime import datetime, timezone
from PySide6.QtCore import QDate, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QDateEdit, QProgressBar, QFormLayout, QGroupBox, QComboBox, QCheckBox,
)
from backend.tle.spacetrack_fetcher import SpaceTrackTLEFetcher
from backend.utils.file_handler import WorkerThread


class SpaceTrackTLEDialog(QDialog):
    authentication_lost = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fetcher_thread = None
        self.tle_data = None
        self._closed = False
        self.setWindowTitle('Fetch TLE from Space-Track')
        self.setModal(True)
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        title = QLabel('Fetch TLE Data from Space-Track')
        title.setStyleSheet('font-size: 16px; font-weight: bold;')
        layout.addWidget(title)
        instructions = QLabel('Enter up to 100 NORAD IDs separated by commas. Both dates are included in UTC. Completed historical date ranges are cached locally.')
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        group = QGroupBox('Parameters')
        form = QFormLayout(group)
        self.norad_input = QLineEdit()
        self.norad_input.setPlaceholderText('25544 or 25544, 25545, 25546')
        form.addRow('NORAD ID(s):', self.norad_input)
        self.date_field = QComboBox()
        self.date_field.addItem('Publication date', 'CREATION_DATE')
        self.date_field.addItem('TLE epoch', 'EPOCH')
        form.addRow('Date field:', self.date_field)
        dates = QHBoxLayout()
        today = datetime.now(timezone.utc).date()
        current = QDate(today.year, today.month, today.day)
        self.start_date, self.end_date = QDateEdit(), QDateEdit()
        for widget in (self.start_date, self.end_date):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat('yyyy-MM-dd')
            widget.setMinimumDate(QDate(1957, 1, 1))
            widget.setMaximumDate(current)
        self.start_date.setDate(current.addDays(-7))
        self.end_date.setDate(current)
        dates.addWidget(self.start_date)
        dates.addWidget(QLabel('to'))
        dates.addWidget(self.end_date)
        form.addRow('Date range (UTC):', dates)
        self.cache_check = QCheckBox('Use cached history when available')
        self.cache_check.setChecked(True)
        form.addRow('', self.cache_check)
        layout.addWidget(group)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel('')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.clicked.connect(self.reject)
        self.fetch_button = QPushButton('Fetch TLE')
        self.fetch_button.setDefault(True)
        self.fetch_button.clicked.connect(self._on_fetch_clicked)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.fetch_button)
        layout.addLayout(buttons)

    def _on_fetch_clicked(self):
        if self.fetcher_thread is not None or self._closed:
            return
        try:
            norad_ids = sorted(set(int(value.strip()) for value in self.norad_input.text().split(',')))
            if not norad_ids or len(norad_ids) > 100 or any(not 1 <= value <= 339999 for value in norad_ids):
                raise ValueError()
        except ValueError:
            self._show_error('Enter up to 100 catalog numbers between 1 and 339999, separated by commas.')
            return
        start, end = self.start_date.date().toPython(), self.end_date.date().toPython()
        if start > end:
            self._show_error('Start date must not be after end date.')
            return
        self._set_inputs_enabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText('Starting fetch...')
        self.fetcher_thread = SpaceTrackTLEFetcher(norad_ids, start, end, self.date_field.currentData(), self.cache_check.isChecked())
        self.fetcher_thread.progress_update.connect(self._on_progress_update)
        self.fetcher_thread.fetch_complete.connect(self._on_fetch_complete)
        self.fetcher_thread.authentication_failed.connect(self._on_authentication_failed)
        self.fetcher_thread.finished.connect(self._on_finished)
        self.fetcher_thread.start()

    @Slot(str)
    def _on_progress_update(self, message):
        if not self._closed and self.sender() is self.fetcher_thread:
            self.status_label.setText(message)

    @Slot(bool, str, str)
    def _on_fetch_complete(self, success, message, tle_data):
        if self._closed or WorkerThread.shutting_down or self.sender() is not self.fetcher_thread:
            return
        self.progress_bar.setVisible(False)
        if success:
            self.tle_data = tle_data
            self.accept()
        else:
            self._show_error(message)

    @Slot()
    def _on_authentication_failed(self):
        if not self._closed and not WorkerThread.shutting_down:
            self.authentication_lost.emit()

    @Slot()
    def _on_finished(self):
        if self.sender() is self.fetcher_thread:
            self.fetcher_thread = None
            if not self._closed:
                self.progress_bar.setVisible(False)
                self._set_inputs_enabled(True)

    def _show_error(self, message):
        self.status_label.setText(message)

    def _set_inputs_enabled(self, enabled):
        for widget in (self.norad_input, self.start_date, self.end_date, self.date_field, self.cache_check, self.fetch_button):
            widget.setEnabled(enabled)

    def get_tle_data(self):
        return self.tle_data

    def done(self, result):
        self._closed = True
        if self.fetcher_thread is not None:
            self.fetcher_thread.stop()
        super().done(result)
