from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QDialog, QMessageBox
from PySide6.QtCore import Signal, Slot, QTimer
from PySide6.QtGui import QAction
from ui.sidebar import Sidebar
from ui.tab_manager import TabManager
from ui.dialogs.rename_dialog import RenameDialog
from ui.dialogs.delete_confirm_dialog import DeleteConfirmDialog
from ui.dialogs.spacetrack_tle_dialog import SpaceTrackTLEDialog
from backend.utils.file_handler import open_tle_file, WorkerThread
from backend.utils.auth_config import AuthConfig


class MainWindow(QMainWindow):
    load_tle_requested = Signal(str)
    load_spacetrack_tle_requested = Signal(str)
    rename_requested = Signal(str, str)
    table_requested = Signal(str)
    plot_requested = Signal(str)
    propagate_requested = Signal(str)
    ground_trace_requested = Signal(str)
    delete_requested = Signal(str)
    export_csv_requested = Signal(str)
    export_tle_requested = Signal(str, str)
    authentication_lost = Signal()
    closing = Signal()

    def __init__(self):
        super().__init__()
        self.import_busy = False
        self._closing = False
        self.setWindowTitle('Orbital Retrieval and Behaviour Inspection Tool for TLEs')
        self._setup_ui()
        self._create_menubar()
        self._connect_signals()
        self.statusBar().showMessage('All epochs and propagation times are UTC.')

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar, self.tab_manager = Sidebar(), TabManager()
        layout.addWidget(self.sidebar)
        layout.addWidget(self.tab_manager, 1)

    def _create_menubar(self):
        insert_menu = self.menuBar().addMenu('Insert')
        self.insert_local = QAction('Insert Local TLE', self)
        self.insert_local.triggered.connect(self._on_insert_local_tle)
        insert_menu.addAction(self.insert_local)
        self.insert_spacetrack = QAction('Insert from SpaceTrack', self)
        self.insert_spacetrack.triggered.connect(self._on_insert_spacetrack_tle)
        self.insert_spacetrack.setEnabled(False)
        insert_menu.addAction(self.insert_spacetrack)
        login_menu = self.menuBar().addMenu('Login')
        self.login_action = QAction('Login to Space-Track', self)
        login_menu.addAction(self.login_action)
        self.logout_action = QAction('Logout', self)
        self.logout_action.setVisible(False)
        login_menu.addAction(self.logout_action)

    def _connect_signals(self):
        self.sidebar.rename_requested.connect(self._on_rename_requested)
        self.sidebar.delete_requested.connect(self._on_delete_requested)
        for name in ('table_requested', 'plot_requested', 'propagate_requested',
                     'ground_trace_requested', 'export_csv_requested', 'export_tle_requested'):
            getattr(self.sidebar, name).connect(getattr(self, name).emit)

    def _on_insert_local_tle(self):
        filepath = open_tle_file()
        if filepath and not self._closing:
            self.load_tle_requested.emit(filepath)

    def _on_insert_spacetrack_tle(self):
        dialog = SpaceTrackTLEDialog(self)
        dialog.authentication_lost.connect(self.authentication_lost.emit)
        try:
            if dialog.exec() and not self._closing:
                data = dialog.get_tle_data()
                if data:
                    self.load_spacetrack_tle_requested.emit(data)
        finally:
            dialog.deleteLater()

    def _on_rename_requested(self, satellite_id):
        dialog = RenameDialog(self.sidebar.get_satellite_name(satellite_id), self)
        try:
            if dialog.exec() and not self._closing:
                self.rename_requested.emit(satellite_id, dialog.get_name())
        finally:
            dialog.deleteLater()

    def _on_delete_requested(self, satellite_id):
        dialog = DeleteConfirmDialog(self.sidebar.get_satellite_name(satellite_id), self)
        try:
            if dialog.exec() and not self._closing:
                self.delete_requested.emit(satellite_id)
        finally:
            dialog.deleteLater()

    def add_satellite_to_sidebar(self, satellite):
        self.sidebar.add_satellite_item(satellite.satellite_id, satellite.name)

    def update_satellite_name(self, satellite_id, new_name):
        self.sidebar.update_satellite_name(satellite_id, new_name)
        self.tab_manager.update_tab_names(satellite_id, new_name)

    def remove_satellite(self, satellite_id):
        self.sidebar.remove_satellite_item(satellite_id)
        self.tab_manager.close_tabs_for_satellite(satellite_id)

    def show_satellite_table(self, satellite_id, name, dataframe):
        self.tab_manager.create_tabular_tab(satellite_id, name, dataframe)

    def show_satellite_plot(self, satellite_id, name, dataframe):
        self.tab_manager.create_plot_tab(satellite_id, name, dataframe)

    def show_satellite_propagator(self, satellite_id, name, propagation_data, propagator_controller):
        self.tab_manager.create_propagator_tab(satellite_id, name, propagation_data, propagator_controller)

    def show_satellite_ground_trace(self, satellite_id, name, ground_trace_data, ground_trace_controller):
        self.tab_manager.create_ground_trace_tab(satellite_id, name, ground_trace_data, ground_trace_controller)

    def update_login_menu_state(self, login_action, logout_action, spacetrack_insert_action):
        self.login_action, self.logout_action, self.insert_spacetrack = login_action, logout_action, spacetrack_insert_action

    @Slot(bool)
    def set_import_busy(self, busy):
        self.import_busy = busy
        self.insert_local.setEnabled(not busy)
        self.insert_spacetrack.setEnabled(not busy and AuthConfig().is_authenticated())
        self.statusBar().showMessage('Reading and sorting TLE records...' if busy else 'All epochs and propagation times are UTC.')

    @Slot(str, str)
    def show_error(self, title, message):
        if not self._closing:
            QMessageBox.critical(self, title, message)

    def closeEvent(self, event):
        if not self._closing:
            self._closing = True
            self.closing.emit()
            for dialog in self.findChildren(QDialog):
                dialog.reject()
            self.tab_manager.close_all()
            WorkerThread.cancel_all()
        if WorkerThread.active:
            self.statusBar().showMessage('Closing active operations...')
            self.setEnabled(False)
            event.ignore()
            QTimer.singleShot(100, self.close)
        else:
            event.accept()
