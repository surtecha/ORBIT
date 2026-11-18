from concurrent.futures import CancelledError
from functools import lru_cache
import numpy as np
from skyfield.api import EarthSatellite, load, wgs84
from backend.propagator.sgp4_propagator import as_utc, make_time_grid, CHUNK_SIZE


@lru_cache(maxsize=1)
def _timescale():
    return load.timescale(builtin=True)


def _convert_times(times, tle_line1, tle_line2, cancelled=None):
    ts = _timescale()
    satellite = EarthSatellite(tle_line1, tle_line2, ts=ts)
    latitudes = np.full(len(times), np.nan)
    longitudes = np.full(len(times), np.nan)
    altitudes = np.full(len(times), np.nan)
    valid = np.zeros(len(times), dtype=bool)
    errors = set()
    for offset in range(0, len(times), CHUNK_SIZE):
        if cancelled and cancelled():
            raise CancelledError()
        batch = times[offset:offset + CHUNK_SIZE]
        geocentric = satellite.at(ts.from_datetimes([as_utc(time) for time in batch]))
        position = wgs84.geographic_position_of(geocentric)
        end = offset + len(batch)
        latitudes[offset:end] = position.latitude.degrees
        longitudes[offset:end] = position.longitude.degrees
        altitudes[offset:end] = position.elevation.km
        messages = np.asarray(geocentric.message, dtype=object)
        if messages.ndim == 0:
            messages = np.full(len(batch), messages.item(), dtype=object)
        successful = np.array([not message for message in messages], dtype=bool)
        errors.update(str(message) for message in messages if message)
        valid[offset:end] = successful
    valid &= np.isfinite(latitudes) & np.isfinite(longitudes) & np.isfinite(altitudes)
    if cancelled and cancelled():
        raise CancelledError()
    return latitudes, longitudes, altitudes, valid, sorted(errors)


def convert_trajectory(times, tle_line1, tle_line2, cancelled=None):
    times = list(times)
    if not times:
        return np.array([]), np.array([]), np.array([])
    latitudes, longitudes, altitudes, valid, errors = _convert_times(times, tle_line1, tle_line2, cancelled)
    if not valid.all():
        raise ValueError('Some positions could not be calculated. ' + '; '.join(errors))
    return latitudes, longitudes, altitudes


def geographic_trajectory(tle_line1, tle_line2, start_time, stop_time, step_seconds=60, cancelled=None):
    times = make_time_grid(start_time, stop_time, step_seconds)
    latitudes, longitudes, altitudes, valid, errors = _convert_times(times, tle_line1, tle_line2, cancelled)
    if not valid.any():
        raise ValueError('SGP4 produced no valid positions. ' + '; '.join(errors))
    indices = np.flatnonzero(valid)
    return {
        'times': [times[index] for index in indices],
        'latitudes': latitudes[valid],
        'longitudes': longitudes[valid],
        'altitudes': altitudes[valid],
        'sample_indices': indices,
        'failed_samples': int((~valid).sum()),
        'errors': errors,
        'start_time': as_utc(start_time),
        'stop_time': as_utc(stop_time),
    }
