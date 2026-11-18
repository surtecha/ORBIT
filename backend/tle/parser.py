import calendar
import math
import re
from pathlib import Path
from concurrent.futures import CancelledError
import pandas as pd
from sgp4.api import Satrec
from sgp4.alpha5 import from_alpha5
from sgp4.conveniences import sat_epoch_datetime


COLUMNS = [
    'time', 'a', 'apogee', 'perigee', 'e', 'i', 'raan', 'aop', 'ma',
    'bstar', 'mean_motion', 'mean_motion_derivative', 'revolution_number',
]


def _check_cancelled(cancelled):
    if cancelled and cancelled():
        raise CancelledError()


def _validate_line(line, number, line_number):
    if len(line) != 69 or not line.startswith(f'{number} '):
        raise ValueError(f'Line {line_number}: expected a 69-character TLE line {number}.')
    if not line.isascii() or not line[68].isdigit():
        raise ValueError(f'Line {line_number}: invalid characters or missing checksum.')
    checksum = sum(int(char) if char.isdigit() else int(char == '-') for char in line[:68]) % 10
    if checksum != int(line[68]):
        raise ValueError(f'Line {line_number}: incorrect TLE checksum.')
    if not re.fullmatch(r'(?:[0-9 ]{5}|[A-HJ-NP-Z][0-9]{4})', line[2:7]):
        raise ValueError(f'Line {line_number}: invalid catalog number.')
    try:
        if from_alpha5(line[2:7]) <= 0:
            raise ValueError()
    except (ValueError, IndexError):
        raise ValueError(f'Line {line_number}: invalid catalog number.') from None


def _parse_pair(line1, line2, line_number, second_number=None):
    _validate_line(line1, 1, line_number)
    _validate_line(line2, 2, second_number or line_number + 1)
    if from_alpha5(line1[2:7]) != from_alpha5(line2[2:7]):
        raise ValueError(f'Line {line_number}: TLE lines refer to different objects.')
    try:
        if not re.fullmatch(r'[0-9]{2}', line1[18:20]):
            raise ValueError('invalid epoch year')
        year = int(line1[18:20])
        year += 1900 if year >= 57 else 2000
        epoch_day = float(line1[20:32])
        if not math.isfinite(epoch_day) or not 0 <= epoch_day < 366 + int(calendar.isleap(year)):
            raise ValueError('invalid epoch day')
        for field in (line1[44:52], line1[53:61]):
            if not re.fullmatch(r'[ +\-][0-9 ]{5}[+\-][0-9]', field):
                raise ValueError('invalid exponent field')
        if not re.fullmatch(r'[0-9]{7}', line2[26:33]):
            raise ValueError('invalid eccentricity')
        for field in (line1[33:43], line2[8:16], line2[17:25], line2[34:42], line2[43:51], line2[52:63]):
            if not math.isfinite(float(field)):
                raise ValueError('non-finite orbital element')
        if not 0 <= float(line2[8:16]) <= 180:
            raise ValueError('invalid inclination')
        if any(not 0 <= float(line2[start:end]) < 360 for start, end in ((17, 25), (34, 42), (43, 51))):
            raise ValueError('invalid angular element')
        int(line1[64:68])
        int(line2[63:68])
        satellite = Satrec.twoline2rv(line1, line2)
        if not 0 <= satellite.ecco < 1 or not 0 <= satellite.inclo <= math.pi:
            raise ValueError('invalid eccentricity or inclination')
        if satellite.no_kozai <= 0 or not math.isfinite(satellite.no_kozai):
            raise ValueError('mean motion must be positive')
        epoch = sat_epoch_datetime(satellite)
        a = satellite.a * satellite.radiusearthkm
        if not math.isfinite(a) or a <= 0:
            raise ValueError('invalid semi-major axis')
    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError(f'Line {line_number}: invalid TLE ({exc}).') from exc
    row = {
        'time': epoch,
        'a': a,
        'apogee': a * (1 + satellite.ecco) - satellite.radiusearthkm,
        'perigee': a * (1 - satellite.ecco) - satellite.radiusearthkm,
        'e': satellite.ecco,
        'i': math.degrees(satellite.inclo),
        'raan': math.degrees(satellite.nodeo),
        'aop': math.degrees(satellite.argpo),
        'ma': math.degrees(satellite.mo),
        'bstar': satellite.bstar,
        'mean_motion': satellite.no_kozai * 1440 / (2 * math.pi),
        'mean_motion_derivative': satellite.ndot * 1440 ** 2 / (2 * math.pi),
        'revolution_number': satellite.revnum,
    }
    if not all(math.isfinite(value) for key, value in row.items() if key != 'time'):
        raise ValueError(f'Line {line_number}: non-finite orbital element.')
    return str(satellite.satnum), row


def parse_tle_text(text, cancelled=None):
    groups = {}
    pending = None
    pending_number = 0
    name = ''
    for number, raw in enumerate(text.lstrip('\ufeff').splitlines(), 1):
        _check_cancelled(cancelled)
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith('1 '):
            if pending is not None:
                raise ValueError(f'Line {pending_number}: missing TLE line 2.')
            pending, pending_number = line, number
        elif line.startswith('2 '):
            if pending is None:
                raise ValueError(f'Line {number}: TLE line 2 has no matching line 1.')
            norad_id, row = _parse_pair(pending, line, pending_number, number)
            group = groups.setdefault(norad_id, {'name': name, 'records': [], 'seen': set()})
            pair = (pending, line)
            if pair not in group['seen']:
                group['seen'].add(pair)
                group['records'].append((row, pair))
            if name and not group['name']:
                group['name'] = name
            pending, name = None, ''
        else:
            if pending is not None:
                raise ValueError(f'Line {number}: expected TLE line 2.')
            if name:
                raise ValueError(f'Line {number}: unexpected text between TLE records.')
            name = line[2:].strip() if line.startswith('0 ') else line.strip()
            if not name:
                raise ValueError(f'Line {number}: empty object name.')
    if pending is not None:
        raise ValueError(f'Line {pending_number}: missing TLE line 2.')
    if name:
        raise ValueError('The final object name has no TLE record.')
    if not groups:
        raise ValueError('No TLE records were found.')
    results = []
    for norad_id, group in groups.items():
        _check_cancelled(cancelled)
        records = sorted(group['records'], key=lambda record: record[0]['time'])
        frame = pd.DataFrame([record[0] for record in records], columns=COLUMNS)
        frame['time'] = pd.to_datetime(frame['time'], utc=True)
        results.append({
            'norad_id': norad_id,
            'name': group['name'] or norad_id,
            'dataframe': frame,
            'tle_lines': [record[1] for record in records],
        })
    return results


def parse_tle_file(filepath, split_objects=False, cancelled=None):
    _check_cancelled(cancelled)
    text = Path(filepath).read_text(encoding='utf-8-sig')
    results = parse_tle_text(text, cancelled=cancelled)
    if split_objects:
        return results
    if len(results) != 1:
        raise ValueError('The file contains multiple objects; use split_objects=True.')
    return results[0]
