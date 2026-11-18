from ui.main_window import MainWindow
from backend.controllers.tle_controller import TLEController
from backend.controllers.login_controller import LoginController
from backend.controllers.propagator_controller import PropagatorController
from backend.controllers.ground_trace_controller import GroundTraceController


class AppController:
    def __init__(self):
        self.main_window = MainWindow()
        self.tle_controller = TLEController()
        self.login_controller = LoginController(self.main_window)
        self.propagator_controller = PropagatorController(self.tle_controller)
        self.ground_trace_controller = GroundTraceController(self.tle_controller)
        self._connect_signals()
        self._update_login_menu()

    def _connect_signals(self):
        window, tle = self.main_window, self.tle_controller
        for signal, slot in (
            (window.load_tle_requested, tle.load_tle),
            (window.load_spacetrack_tle_requested, tle.load_spacetrack_tle),
            (window.rename_requested, tle.rename_satellite),
            (window.table_requested, tle.get_satellite_data),
            (window.plot_requested, tle.get_satellite_plot_data),
            (window.delete_requested, tle.delete_satellite),
            (window.export_csv_requested, tle.export_csv),
            (window.export_tle_requested, tle.export_tle),
            (tle.satellite_added, window.add_satellite_to_sidebar),
            (tle.satellite_renamed, window.update_satellite_name),
            (tle.satellite_removed, window.remove_satellite),
            (tle.satellite_data_ready, window.show_satellite_table),
            (tle.satellite_plot_ready, window.show_satellite_plot),
            (tle.busy_changed, window.set_import_busy),
            (window.propagate_requested, self.propagator_controller.propagate_satellite),
            (window.ground_trace_requested, self.ground_trace_controller.initiate_ground_trace),
            (window.login_action.triggered, self.login_controller.handle_login_click),
            (window.logout_action.triggered, self.login_controller.handle_logout_click),
            (window.authentication_lost, self.login_controller.on_authentication_lost),
        ):
            signal.connect(slot)
        for controller in (tle, self.propagator_controller, self.ground_trace_controller):
            controller.operation_failed.connect(window.show_error)
        self.propagator_controller.propagation_data_ready.connect(
            lambda satellite_id, name, data: window.show_satellite_propagator(satellite_id, name, data, self.propagator_controller))
        self.ground_trace_controller.ground_trace_data_ready.connect(
            lambda satellite_id, name, data: window.show_satellite_ground_trace(satellite_id, name, data, self.ground_trace_controller))
        self.login_controller.login_status_changed.connect(self._on_login_status_changed)
        window.closing.connect(self.login_controller.shutdown)
        window.closing.connect(tle.shutdown)

    def _update_login_menu(self):
        self.login_controller.update_menu_state(self.main_window.login_action, self.main_window.logout_action,
                                                self.main_window.insert_spacetrack)

    def _on_login_status_changed(self, logged_in):
        self._update_login_menu()

    def show(self):
        self.main_window.showMaximized()
