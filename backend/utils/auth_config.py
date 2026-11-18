from threading import RLock
from PySide6.QtCore import QSettings


class AuthConfig:
    _credentials = None
    _authenticated = False
    _persistent = False
    _lock = RLock()
    _service = 'ORBITT.SpaceTrack'

    def __init__(self):
        self.settings = QSettings('ORBITT', 'SpaceTrack')

    @staticmethod
    def _secure_store():
        try:
            import keyring
            store = keyring.get_keyring()
            stores = getattr(store, 'backends', [store])
            trusted = (
                'keyring.backends.macOS', 'keyring.backends.Windows',
                'keyring.backends.SecretService', 'keyring.backends.libsecret',
                'keyring.backends.kwallet',
            )
            for candidate in stores:
                if type(candidate).__module__.startswith(trusted) and candidate.priority > 0:
                    return candidate
        except Exception:
            pass
        return None

    def _delete_saved_password(self, email):
        store = self._secure_store()
        if store is not None and email:
            try:
                store.delete_password(self._service, email)
            except Exception:
                pass

    def get_credentials(self):
        with self._lock:
            if AuthConfig._credentials is not None:
                return AuthConfig._credentials
            email = str(self.settings.value('email', '') or '').strip()
            legacy = str(self.settings.value('password', '') or '')
            password = legacy
            remember = self.settings.value('remember_password', True, type=bool)
            store = self._secure_store() if remember or legacy else None
            if store is not None and email:
                try:
                    if legacy:
                        store.set_password(self._service, email, legacy)
                    password = store.get_password(self._service, email) or legacy
                    AuthConfig._persistent = bool(password)
                except Exception:
                    AuthConfig._persistent = False
            self.settings.remove('password')
            self.settings.setValue('remember_password', AuthConfig._persistent)
            self.settings.sync()
            AuthConfig._credentials = (email, password)
            return AuthConfig._credentials

    def save_credentials(self, email, password, remember=True):
        email = str(email).strip()
        with self._lock:
            old_email, _ = self.get_credentials()
            if old_email and (old_email != email or not remember):
                self._delete_saved_password(old_email)
            AuthConfig._credentials = (email, password)
            AuthConfig._persistent = False
            self.settings.setValue('email', email)
            self.settings.remove('password')
            store = self._secure_store() if remember else None
            if store is not None:
                try:
                    store.set_password(self._service, email, password)
                    AuthConfig._persistent = store.get_password(self._service, email) == password
                except Exception:
                    AuthConfig._persistent = False
            self.settings.setValue('remember_password', AuthConfig._persistent)
            self.settings.sync()
            return AuthConfig._persistent

    def has_credentials(self):
        email, password = self.get_credentials()
        return bool(email and password)

    def is_authenticated(self):
        with self._lock:
            return AuthConfig._authenticated

    def set_authenticated(self, authenticated):
        with self._lock:
            AuthConfig._authenticated = bool(authenticated)

    def clear_credentials(self):
        with self._lock:
            email, _ = self.get_credentials()
            self._delete_saved_password(email)
            AuthConfig._credentials = ('', '')
            AuthConfig._authenticated = False
            AuthConfig._persistent = False
            self.settings.remove('email')
            self.settings.remove('password')
            self.settings.remove('remember_password')
            self.settings.sync()
