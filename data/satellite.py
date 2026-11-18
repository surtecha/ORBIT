from dataclasses import dataclass, field
import pandas as pd


@dataclass
class SatelliteData:
    satellite_id: str
    norad_id: str
    name: str
    dataframe: pd.DataFrame
    tle_lines: list = field(default_factory=list)

    def __post_init__(self):
        self.norad_id = str(self.norad_id)
        self.name = str(self.name).strip() or self.norad_id
        self.tle_lines = list(self.tle_lines or [])
        if len(self.dataframe) != len(self.tle_lines):
            raise ValueError('Every data row must have exactly one matching TLE pair.')
        if self.dataframe.empty or 'time' not in self.dataframe:
            raise ValueError('A satellite must contain at least one epoch.')
        frame = self.dataframe.copy().reset_index(drop=True)
        frame['time'] = pd.to_datetime(frame['time'], utc=True, errors='raise')
        if frame['time'].isna().any():
            raise ValueError('TLE epochs cannot be empty.')
        order = frame.sort_values('time', kind='stable').index
        seen, keep, pairs = set(), [], []
        for index in order:
            pair = tuple(self.tle_lines[index])
            if len(pair) != 2:
                raise ValueError('Each TLE must contain two lines.')
            if pair not in seen:
                seen.add(pair)
                keep.append(index)
                pairs.append(pair)
        self.dataframe = frame.iloc[keep].reset_index(drop=True)
        self.tle_lines = pairs

    @property
    def latest_record(self):
        line1, line2 = self.tle_lines[-1]
        return line1, line2, self.dataframe['time'].iloc[-1].to_pydatetime()
