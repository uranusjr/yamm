import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import cascaded_union, transform

from yamm.constructs.coordinate import Coordinate
from yamm.constructs.geofence import Geofence
from yamm.constructs.trace import Trace
from yamm.utils.crs import LATLON_CRS, XY_CRS


def get_trace(sampno, vehno, table, engine):
    q = f"""
    select * from {table}  
    where sampno={sampno} and vehno={vehno}
    order by time_local
    """
    trip_df = pd.read_sql(q, engine)

    gdf = gpd.GeoDataFrame(trip_df, geometry=gpd.points_from_xy(trip_df.longitude, trip_df.latitude), crs=LATLON_CRS)
    gdf = gdf.to_crs(XY_CRS)

    coords = [Coordinate(geom=g, crs=XY_CRS) for g in gdf.geometry]
    crs = XY_CRS

    return Trace(coords, crs)


def compute_bbox_from_table(table, padding, engine):
    q = f"""
    select min(latitude) as lat_min, max(latitude) as lat_max,
    min(longitude) as lon_min, max(longitude) as lon_max
    from {table} 
    """
    df = pd.read_sql(q, engine)
    b = df.iloc[0]

    bbox = box(b.lon_min - padding, b.lat_min - padding, b.lon_max + padding, b.lat_max + padding)

    return Geofence(geometry=bbox, crs=LATLON_CRS)


def compute_polygon_from_table(table, limit, offset, engine, xy=False, padding=15, buffer_res=16):
    q = f"""
    select *
    from {table}
    limit {limit} offset {offset}
    """
    df = pd.read_sql(q, engine)

    transformer = Transformer.from_crs(LATLON_CRS, XY_CRS)
    new_x, new_y = transformer.transform(list(df.latitude), list(df.longitude))

    coords = gpd.GeoSeries(gpd.points_from_xy(new_x, new_y))

    polygon = cascaded_union(coords.buffer(padding, buffer_res))

    if xy:
        return Geofence(crs=XY_CRS, geometry=polygon)

    project = Transformer.from_crs(XY_CRS, LATLON_CRS, always_xy=True).transform
    polygon = transform(project, polygon)

    return Geofence(crs=LATLON_CRS, geometry=polygon)


def get_unique_trips(table, engine):
    q = f"""
    select sampno, vehno from {table} 
    group by sampno, vehno
    """
    trips = pd.read_sql(q, engine)

    return trips


def matches_to_dataframe(matches):
    return pd.DataFrame([m.to_json() for m in matches])
