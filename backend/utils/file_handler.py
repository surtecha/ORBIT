from pathlib import Path
from threading import Event
from concurrent.futures import CancelledError
from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtWidgets import QFileDialog


class WorkerThread(QThread):
    active = set()
    shutting_down = False

    def __init__(self):
        super().__init__()
        self._cancelled = Event()
        self.finished.connect(self._release)

    def start(self, priority=QThread.Priority.InheritPriority):
        if self.shutting_down:
            return
        self.active.add(self)
        try:
            super().start(priority)
        except Exception:
            self.active.discard(self)
            raise

    @Slot()
    def _release(self):
        self.active.discard(self)
        self.deleteLater()

    def is_cancelled(self):
        return self._cancelled.is_set()

    def stop(self):
        self._cancelled.set()
        if self.isRunning():
            self.requestInterruption()

    @classmethod
    def cancel_all(cls):
        cls.shutting_down = True
        for worker in tuple(cls.active):
            worker.stop()


class TaskWorker(WorkerThread):
    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            if self.is_cancelled():
                return
            result = self.function(*self.args, **self.kwargs, cancelled=self.is_cancelled)
            if not self.is_cancelled():
                self.result_ready.emit(result)
        except CancelledError:
            pass
        except Exception as exc:
            if not self.is_cancelled():
                self.failed.emit(str(exc) or type(exc).__name__)
        finally:
            self.function = None
            self.args = ()
            self.kwargs = {}


_last_directory = ''


def open_tle_file():
    global _last_directory
    filepath, _ = QFileDialog.getOpenFileName(
        None, 'Select TLE File', _last_directory,
        'TLE Files (*.tle *.txt);;All Files (*.*)',
    )
    if filepath:
        _last_directory = str(Path(filepath).parent)
        return filepath
    return None


def _validate_tle_file(filepath):
    from backend.tle.parser import parse_tle_file
    try:
        parse_tle_file(filepath, split_objects=True)
        return True
    except (OSError, ValueError):
        return False
