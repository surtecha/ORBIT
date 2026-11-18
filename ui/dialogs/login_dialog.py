from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QCheckBox,
)
from backend.utils.spacetrack import SpaceTrackAuth, validate_spacetrack_credentials
from backend.utils.auth_config import AuthConfig
from backend.utils.file_handler import WorkerThread


class LoginDialog(QDialog):
    login_success = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth_config = AuthConfig()
        self.auth_thread = None
        self._attempt = None
        self._closed = False
        self.setWindowTitle('Login to Space-Track')
        self.setModal(True)
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        title = QLabel('Space-Track Login')
        title.setStyleSheet('font-size: 16px; font-weight: bold;')
        layout.addWidget(title)
        instructions = QLabel('Enter your Space-Track credentials. Register or review account notices at space-track.org.')
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        layout.addWidget(QLabel('Email:'))
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText('your.email@example.com')
        self.email_input.setText(self.auth_config.get_credentials()[0])
        layout.addWidget(self.email_input)
        layout.addWidget(QLabel('Password:'))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_input)
        self.remember_check = QCheckBox('Remember securely on this device')
        self.remember_check.setChecked(True)
        layout.addWidget(self.remember_check)
        self.status_label = QLabel('')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.clicked.connect(self.reject)
        self.login_button = QPushButton('Login')
        self.login_button.setDefault(True)
        self.login_button.clicked.connect(self._on_login_clicked)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.login_button)
        layout.addLayout(buttons)

    def _on_login_clicked(self):
        if self.auth_thread is not None or self._closed:
            return
        email, password = self.email_input.text().strip(), self.password_input.text()
        valid, message = validate_spacetrack_credentials(email, password)
        if not valid:
            self.status_label.setText(message)
            return
        self._attempt = (email, password, self.remember_check.isChecked())
        self._set_inputs_enabled(False)
        self.status_label.setText('Authenticating...')
        self.auth_thread = SpaceTrackAuth(email, password)
        self.auth_thread.login_result.connect(self._on_login_result)
        self.auth_thread.finished.connect(self._on_auth_finished)
        self.auth_thread.start()

    @Slot(bool, str)
    def _on_login_result(self, success, message):
        if self._closed or WorkerThread.shutting_down or self.sender() is not self.auth_thread:
            return
        if not success:
            self.status_label.setText(message)
            self._attempt = None
            return
        email, password, remember = self._attempt
        persistent = self.auth_config.save_credentials(email, password, remember)
        self.auth_config.set_authenticated(True)
        self._attempt = None
        self.password_input.clear()
        self.login_success.emit()
        if remember and not persistent:
            QMessageBox.information(
                self, 'Login Successful',
                'You are logged in for this session. A secure credential store is unavailable, so the password was not saved. '
                'Install keyring and enable your operating system credential store to remember it.',
            )
        self.accept()

    @Slot()
    def _on_auth_finished(self):
        if self.sender() is self.auth_thread:
            self.auth_thread = None
            if not self._closed:
                self._set_inputs_enabled(True)

    def _set_inputs_enabled(self, enabled):
        for widget in (self.email_input, self.password_input, self.remember_check, self.login_button):
            widget.setEnabled(enabled)

    def done(self, result):
        self._closed = True
        self._attempt = None
        self.password_input.clear()
        if self.auth_thread is not None:
            self.auth_thread.stop()
        super().done(result)
