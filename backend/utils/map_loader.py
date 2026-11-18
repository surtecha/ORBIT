from pathlib import Path
import geopandas as gpd


class MapLoader:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._world_map = None
            cls._instance._loaded = False
            cls._instance.error = ''
        return cls._instance

    def load_world_map(self):
        if self._loaded:
            return self._world_map
        self._loaded = True
        path = Path(__file__).resolve().parents[2] / 'assets' / 'ne_10m_land' / 'ne_10m_land.shp'
        try:
            if not path.is_file():
                raise FileNotFoundError('The world map asset was not found.')
            world = gpd.read_file(path)
            if world.crs is not None:
                world = world.to_crs(epsg=4326)
            self._world_map = world.geometry.simplify(tolerance=0.01, preserve_topology=True)
        except Exception as exc:
            self.error = f'Map unavailable: {exc}'
        return self._world_map

    def get_world_map(self):
        return self.load_world_map()
