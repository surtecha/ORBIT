from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox
from PySide6.QtCore import Qt


class DeleteConfirmDialog(QDialog):
    def __init__(self, object_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Confirm Deletion')
        self.setModal(True)
        layout = QVBoxLayout(self)
        message = QLabel(f"Are you sure you want to delete '{object_name}'?")
        message.setTextFormat(Qt.TextFormat.PlainText)
        message.setWordWrap(True)
        layout.addWidget(message)
        layout.addWidget(QLabel('This action cannot be undone.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        buttons.button(QDialogButtonBox.StandardButton.No).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
