import hashlib
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote
from concurrent.futures import CancelledError
import requests
from PySide6.QtCore import Signal, QStandardPaths
from backend.utils.auth_config import AuthConfig
from backend.utils.file_handler import WorkerThread
from backend.utils.spacetrack import (
    BASE_URL, AuthenticationError, SpaceTrackError, authenticate_session,
    check_cancelled, check_response, clear_cached_session, request,
)


class SpaceTrackTLEFetcher(WorkerThread):
    progress_update = Signal(str)
    fetch_complete = Signal(bool, str, str)
    authentication_failed = Signal()
    MAX_BYTES = 64 * 1024 * 1024

    def __init__(self, norad_ids, start_date, end_date, date_field='CREATION_DATE', use_cache=True):
        super().__init__()
        self.norad_ids = sorted(set(int(value) for value in norad_ids))
        self.start_date = start_date
        self.end_date = end_date
        self.date_field = date_field
        self.use_cache = bool(use_cache)
        self.auth_config = AuthConfig()
        self.email, self.password = self.auth_config.get_credentials()
        self.session = None

    def run(self):
        try:
            self._validate_parameters()
            cached = self._read_cache()
            if cached is not None:
                if not self.is_cancelled():
                    self.fetch_complete.emit(True, 'Loaded cached TLE history.', cached)
                return
            self.progress_update.emit('Authenticating with Space-Track...')
            self._authenticate()
            self.progress_update.emit(f'Fetching TLE data for {len(self.norad_ids)} object(s)...')
            data = self._fetch_tle_data()
            check_cancelled(self.is_cancelled)
            if data:
                self._write_cache(data)
                self.fetch_complete.emit(True, 'TLE data fetched successfully.', data)
            else:
                self.fetch_complete.emit(False, 'No TLE data was found for these objects and dates.', '')
        except CancelledError:
            pass
        except AuthenticationError as exc:
            if not self.is_cancelled():
                clear_cached_session()
                self.authentication_failed.emit()
                self.fetch_complete.emit(False, str(exc), '')
        except Exception as exc:
            if not self.is_cancelled():
                self.fetch_complete.emit(False, str(exc) or 'The TLE request failed.', '')
        finally:
            self.password = ''
            if self.session is not None:
                self.session.close()
                self.session = None

    def _validate_parameters(self):
        if not self.norad_ids or any(not 1 <= value <= 339999 for value in self.norad_ids):
            raise ValueError('TLE catalog numbers must be between 1 and 339999.')
        if len(self.norad_ids) > 100:
            raise ValueError('Request at most 100 objects at a time.')
        if self.start_date > self.end_date:
            raise ValueError('Start date must not be after end date.')
        if self.end_date > datetime.now(timezone.utc).date():
            raise ValueError('End date cannot be in the future.')
        if self.date_field not in ('CREATION_DATE', 'EPOCH'):
            raise ValueError('Select either publication date or epoch.')

    def _authenticate(self, reuse=True):
        if self.session is not None:
            self.session.close()
        self.session = authenticate_session(self.email, self.password, self.is_cancelled, reuse)
        return True

    def _query_url(self):
        start = self.start_date.strftime('%Y-%m-%d') + ' 00:00:00'
        end = self.end_date.strftime('%Y-%m-%d') + ' 23:59:59.999999'
        ids = ','.join(map(str, self.norad_ids))
        dates = quote(f'{start}--{end}', safe='')
        return (f'{BASE_URL}/basicspacedata/query/class/gp_history/NORAD_CAT_ID/{ids}/'
                f'{self.date_field}/{dates}/orderby/EPOCH%20asc/format/tle/')

    def _fetch_tle_data(self):
        for attempt in range(2):
            response = request(self.session, 'GET', self._query_url(), self.is_cancelled, stream=True)
            try:
                check_response(response, 'TLE query')
                chunks, total = [], 0
                try:
                    for chunk in response.iter_content(chunk_size=65536):
                        check_cancelled(self.is_cancelled)
                        if chunk:
                            total += len(chunk)
                            if total > self.MAX_BYTES:
                                raise SpaceTrackError('The download is too large. Use fewer objects or a shorter date range.')
                            chunks.append(chunk)
                except requests.exceptions.RequestException:
                    raise SpaceTrackError('The download was interrupted. Check your connection and try again.') from None
                data = b''.join(chunks).decode('utf-8-sig').strip()
                if not data or data == '[]':
                    return ''
                if not data.startswith('1 '):
                    if '"Login"' in data and 'Failed' in data:
                        raise AuthenticationError('The Space-Track session has expired.')
                    raise SpaceTrackError('Space-Track returned an error or web page instead of TLE data.')
                return data + '\n'
            except AuthenticationError:
                if attempt:
                    raise
            finally:
                response.close()
            self._authenticate(reuse=False)
        return ''

    def _cache_path(self):
        if self.end_date >= datetime.now(timezone.utc).date():
            return None
        location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        if not location:
            return None
        key = hashlib.sha256(self._query_url().encode()).hexdigest()
        return Path(location) / 'spacetrack_history' / f'{key}.tle'

    def _read_cache(self):
        if not self.use_cache:
            return None
        path = self._cache_path()
        try:
            if path is not None and path.is_file() and path.stat().st_size <= self.MAX_BYTES:
                data = path.read_text(encoding='utf-8')
                if data.startswith('1 '):
                    return data
        except (OSError, UnicodeError):
            pass
        return None

    def _write_cache(self, data):
        path = self._cache_path()
        temporary = None
        try:
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
                    temporary = stream.name
                    stream.write(data)
                os.replace(temporary, path)
                temporary = None
        except OSError:
            pass
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
