from PySide6.QtCore import QObject, Signal, Slot, QTimer
from PySide6.QtWidgets import QMessageBox
from backend.utils.auth_config import AuthConfig
from backend.utils.file_handler import WorkerThread
from backend.utils.spacetrack import SpaceTrackAuth, clear_cached_session
from ui.dialogs.login_dialog import LoginDialog


class LoginController(QObject):
    login_status_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.window = parent
        self.auth_config = AuthConfig()
        self.login_dialog = None
        self.auth_thread = None
        QTimer.singleShot(0, self._restore_login)

    def get_login_status(self):
        return self.auth_config.is_authenticated()

    def get_current_user_email(self):
        return self.auth_config.get_credentials()[0]

    def get_login_display_text(self):
        if self.auth_thread is not None:
            return 'Verifying saved Space-Track login...'
        if self.get_login_status():
            return f'Logged in as: {self.get_current_user_email()}'
        return 'Login to Space-Track'

    def should_show_logout(self):
        return self.get_login_status()

    def should_enable_spacetrack_insert(self):
        return self.get_login_status() and not getattr(self.window, 'import_busy', False)

    def handle_login_click(self):
        if self.auth_thread is None:
            self.open_login_dialog()

    def handle_logout_click(self):
        reply = QMessageBox.question(self.window, 'Logout', 'Log out of Space-Track?',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.shutdown()
            clear_cached_session()
            self.auth_config.clear_credentials()
            self.login_status_changed.emit(False)

    def update_menu_state(self, login_action, logout_action, spacetrack_insert_action):
        login_action.setText(self.get_login_display_text())
        login_action.setEnabled(self.auth_thread is None)
        logout_action.setVisible(self.should_show_logout())
        spacetrack_insert_action.setEnabled(self.should_enable_spacetrack_insert())

    def open_login_dialog(self):
        if self.login_dialog is None:
            self.login_dialog = LoginDialog(self.window)
            self.login_dialog.login_success.connect(self.on_login_success)
            self.login_dialog.finished.connect(self._dialog_finished)
        self.login_dialog.show()
        self.login_dialog.raise_()
        self.login_dialog.activateWindow()

    @Slot()
    def on_login_success(self):
        self.login_status_changed.emit(True)

    @Slot(int)
    def _dialog_finished(self, result):
        if self.sender() is self.login_dialog:
            dialog, self.login_dialog = self.login_dialog, None
            dialog.deleteLater()

    @Slot()
    def _restore_login(self):
        if WorkerThread.shutting_down or self.get_login_status() or self.login_dialog is not None:
            return
        email, password = self.auth_config.get_credentials()
        if not email or not password:
            return
        self.auth_thread = SpaceTrackAuth(email, password)
        self.auth_thread.login_result.connect(self._restored)
        self.auth_thread.finished.connect(self._restore_finished)
        self.login_status_changed.emit(False)
        self.auth_thread.start()

    @Slot(bool, str)
    def _restored(self, success, message):
        if WorkerThread.shutting_down or self.sender() is not self.auth_thread:
            return
        self.auth_config.set_authenticated(success)
        if not success and self.window is not None:
            self.window.statusBar().showMessage(message, 15000)
        self.login_status_changed.emit(success)

    @Slot()
    def _restore_finished(self):
        if self.sender() is self.auth_thread:
            self.auth_thread = None
            self.login_status_changed.emit(self.get_login_status())

    @Slot()
    def on_authentication_lost(self):
        clear_cached_session()
        self.auth_config.set_authenticated(False)
        self.login_status_changed.emit(False)

    def shutdown(self):
        if self.auth_thread is not None:
            self.auth_thread.stop()
            self.auth_thread = None
        if self.login_dialog is not None:
            self.login_dialog.reject()
