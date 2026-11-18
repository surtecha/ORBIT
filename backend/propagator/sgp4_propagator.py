import math
from datetime import datetime, timedelta, timezone
from concurrent.futures import CancelledError
import numpy as np
from sgp4.api import Satrec, SGP4_ERRORS, jday


MAX_SAMPLES = 100000
CHUNK_SIZE = 2048


def as_utc(value):
    if not isinstance(value, datetime):
        raise ValueError('Expected a date and time.')
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def make_time_grid(start_time, stop_time, step_seconds=60):
    start, stop = as_utc(start_time), as_utc(stop_time)
    try:
        seconds = float(step_seconds)
    except (TypeError, ValueError):
        raise ValueError('The time step must be a positive number.') from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('The time step must be a positive number.')
    if not math.isfinite(seconds * 1000000):
        raise ValueError('The time step is too large.')
    step_us = round(seconds * 1000000)
    if step_us <= 0:
        raise ValueError('The time step must be at least one microsecond.')
    delta = stop - start
    duration_us = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
    if duration_us < 0:
        raise ValueError('Stop time must not be earlier than start time.')
    count = duration_us // step_us + 1
    if count > MAX_SAMPLES:
        raise ValueError(f'The requested interval exceeds {MAX_SAMPLES:,} samples. Shorten the time interval.')
    return [start + timedelta(microseconds=index * step_us) for index in range(count)]


def _julian_dates(times):
    return jday(
        np.array([t.year for t in times]), np.array([t.month for t in times]),
        np.array([t.day for t in times]), np.array([t.hour for t in times]),
        np.array([t.minute for t in times]),
        np.array([t.second + t.microsecond / 1000000 for t in times]),
    )


def propagate_orbit(tle_line1, tle_line2, start_time, stop_time, step_seconds=60, cancelled=None):
    times = make_time_grid(start_time, stop_time, step_seconds)
    satellite = Satrec.twoline2rv(tle_line1, tle_line2)
    positions, velocities, codes = [], [], []
    for offset in range(0, len(times), CHUNK_SIZE):
        if cancelled and cancelled():
            raise CancelledError()
        jd, fraction = _julian_dates(times[offset:offset + CHUNK_SIZE])
        errors, position, velocity = satellite.sgp4_array(jd, fraction)
        codes.append(errors)
        positions.append(position)
        velocities.append(velocity)
    errors = np.concatenate(codes)
    positions, velocities = np.concatenate(positions), np.concatenate(velocities)
    valid = (errors == 0) & np.isfinite(positions).all(axis=1) & np.isfinite(velocities).all(axis=1)
    messages = sorted({SGP4_ERRORS.get(int(code), f'SGP4 error {code}') for code in errors if code})
    if not valid.any():
        raise ValueError('SGP4 produced no valid positions. ' + '; '.join(messages))
    indices = np.flatnonzero(valid)
    return {
        'times': [times[index] for index in indices],
        'positions': positions[valid],
        'velocities': velocities[valid],
        'sample_indices': indices,
        'failed_samples': int((~valid).sum()),
        'errors': messages,
    }


def get_orbital_period_minutes(tle_line1, tle_line2):
    satellite = Satrec.twoline2rv(tle_line1, tle_line2)
    if not math.isfinite(satellite.no_kozai) or satellite.no_kozai <= 0:
        raise ValueError('The TLE has an invalid mean motion.')
    return 2 * math.pi / satellite.no_kozai


def compute_position_at_time(tle_line1, tle_line2, target_time):
    target = as_utc(target_time)
    satellite = Satrec.twoline2rv(tle_line1, tle_line2)
    jd, fraction = jday(target.year, target.month, target.day, target.hour,
                        target.minute, target.second + target.microsecond / 1000000)
    error, position, velocity = satellite.sgp4(jd, fraction)
    if error or not np.isfinite(position).all() or not np.isfinite(velocity).all():
        return None, None
    return position, velocity
