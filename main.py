import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from app.app_controller import AppController
from backend.utils.file_handler import WorkerThread
from backend.utils.spacetrack import clear_cached_session


def main():
    application = QApplication(sys.argv)
    application.setApplicationName('ORBITT')
    application.setOrganizationName('ORBITT')
    application.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / 'assets' / 'icon.png')))
    controller = AppController()
    controller.show()
    try:
        return application.exec()
    finally:
        WorkerThread.cancel_all()
        for worker in tuple(WorkerThread.active):
            worker.wait()
        clear_cached_session()


if __name__ == '__main__':
    sys.exit(main())
