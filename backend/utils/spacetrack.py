import hashlib
import time
from collections import deque
from concurrent.futures import CancelledError
from threading import Lock
import requests
from PySide6.QtCore import Signal
from backend.utils.file_handler import WorkerThread


BASE_URL = 'https://www.space-track.org'
TIMEOUT = (5, 30)
_request_times = deque()
_request_lock = Lock()
_session_lock = Lock()
_session_key = None
_session_cookies = None


class SpaceTrackError(Exception):
    pass


class AuthenticationError(SpaceTrackError):
    pass


def check_cancelled(cancelled):
    if cancelled and cancelled():
        raise CancelledError()


def request(session, method, url, cancelled=None, **kwargs):
    check_cancelled(cancelled)
    now = time.monotonic()
    with _request_lock:
        while _request_times and now - _request_times[0] >= 3600:
            _request_times.popleft()
        if len(_request_times) >= 290 or sum(now - stamp < 60 for stamp in _request_times) >= 29:
            raise SpaceTrackError('The local Space-Track request limit has been reached. Try again later.')
        _request_times.append(now)
    try:
        response = session.request(method, url, timeout=TIMEOUT, allow_redirects=False, **kwargs)
    except requests.exceptions.Timeout:
        raise SpaceTrackError('Space-Track did not respond before the connection timed out.') from None
    except requests.exceptions.SSLError:
        raise SpaceTrackError('The secure connection to Space-Track could not be verified. Check your network and system clock.') from None
    except requests.exceptions.RequestException:
        raise SpaceTrackError('Could not connect to Space-Track. Check your network connection.') from None
    try:
        check_cancelled(cancelled)
    except CancelledError:
        response.close()
        raise
    return response


def check_response(response, operation='request'):
    status = response.status_code
    if status in (401, 403):
        raise AuthenticationError('Space-Track denied access. Sign in again and check your account status.')
    if status == 429:
        raise SpaceTrackError('Space-Track is limiting requests. Try again later.')
    if 300 <= status < 400:
        raise SpaceTrackError('Space-Track redirected the API request. Sign in on its website and check for account notices.')
    if status >= 500:
        raise SpaceTrackError(f'Space-Track is temporarily unavailable (HTTP {status}).')
    if not 200 <= status < 300:
        raise SpaceTrackError(f'Space-Track {operation} failed (HTTP {status}).')


def clear_cached_session():
    global _session_key, _session_cookies
    with _session_lock:
        _session_key = None
        _session_cookies = None


def validate_spacetrack_credentials(email, password):
    if not str(email).strip() or not password:
        return False, 'Email and password are required.'
    if '@' not in str(email) or any(char.isspace() for char in str(email).strip()):
        return False, 'Please enter a valid email address.'
    return True, ''


def check_login_failure(data):
    if not isinstance(data, dict):
        return
    login = str(data.get('Login', '')).strip().casefold()
    if login in ('failed', 'failure', 'false', 'denied'):
        raise AuthenticationError('Space-Track rejected the login. Check your email, password, and account status.')
    if any(data.get(field) for field in ('error', 'Error', 'errors')):
        raise SpaceTrackError('Space-Track reported an error. Sign in on its website and check your account status.')


def verify_session(session, cancelled=None):
    url = f'{BASE_URL}/basicspacedata/query/class/gp/limit/1/format/json'
    response = request(session, 'GET', url, cancelled)
    try:
        check_response(response, 'login verification')
        try:
            data = response.json()
        except ValueError:
            raise SpaceTrackError(
                f'Space-Track login verification returned a non-JSON response (HTTP {response.status_code}). '
                'Sign in on its website and check for account notices or network restrictions.'
            ) from None
        check_login_failure(data)
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise SpaceTrackError(
                f'Space-Track login verification returned unexpected data (HTTP {response.status_code}). '
                'Sign in on its website and check your account status.'
            )
    finally:
        response.close()


def authenticate_session(email, password, cancelled=None, reuse=False):
    global _session_key, _session_cookies
    email = str(email).strip()
    valid, message = validate_spacetrack_credentials(email, password)
    if not valid:
        raise AuthenticationError(message)
    key = hashlib.sha256(f'{email}\0{password}'.encode()).digest()
    session = requests.Session()
    session.headers.update({'User-Agent': 'ORBITT/2'})
    try:
        check_cancelled(cancelled)
        with _session_lock:
            if reuse and key == _session_key and _session_cookies is not None:
                session.cookies.update(_session_cookies.copy())
                return session
        response = request(session, 'POST', f'{BASE_URL}/ajaxauth/login', cancelled,
                           data={'identity': email, 'password': password})
        try:
            check_response(response, 'login')
            try:
                data = response.json()
            except ValueError:
                data = None
            check_login_failure(data)
        finally:
            response.close()
        verify_session(session, cancelled)
        check_cancelled(cancelled)
        with _session_lock:
            _session_key = key
            _session_cookies = session.cookies.copy()
        return session
    except BaseException:
        with _session_lock:
            if key == _session_key:
                _session_key = None
                _session_cookies = None
        session.close()
        raise


def create_spacetrack_session(email, password, cancelled=None, reuse=False):
    try:
        return authenticate_session(email, password, cancelled, reuse), True, 'Login successful.'
    except SpaceTrackError as exc:
        return None, False, str(exc)


class SpaceTrackAuth(WorkerThread):
    login_result = Signal(bool, str)

    def __init__(self, email, password):
        super().__init__()
        self.email = email
        self.password = password
        self.session = None

    def run(self):
        try:
            self.session = authenticate_session(self.email, self.password, self.is_cancelled)
            if not self.is_cancelled():
                self.login_result.emit(True, 'Login successful.')
        except CancelledError:
            pass
        except Exception as exc:
            if not self.is_cancelled():
                self.login_result.emit(False, str(exc) or 'Login failed.')
        finally:
            self.password = ''
            if self.session is not None:
                self.session.close()
                self.session = None
