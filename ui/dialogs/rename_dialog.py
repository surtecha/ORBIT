from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QLabel, QDialogButtonBox


class RenameDialog(QDialog):
    def __init__(self, current_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Rename Satellite')
        self.setModal(True)
        self.setMinimumWidth(300)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Enter new name:'))
        self.name_input = QLineEdit(current_name)
        self.name_input.selectAll()
        layout.addWidget(self.name_input)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.name_input.textChanged.connect(lambda text: self.ok_button.setEnabled(bool(text.strip())))
        self.ok_button.setEnabled(bool(current_name.strip()))
        layout.addWidget(buttons)
        self.name_input.setFocus()

    def get_name(self):
        return self.name_input.text().strip()
