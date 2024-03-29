from landsatxplore.api import API
from landsatxplore.earthexplorer import EarthExplorer 
import json
import os
import glob
import numpy as np
import tarfile
from shapely.geometry import Polygon, Point
import geopandas as gpd
from scripts.credential import username_landsat, password_landsat, username_sentinel, password_sentinel
from sentinelsat.sentinel import SentinelAPI
from datetime import datetime
import rasterio as rio
from rasterio import mask, plot
import matplotlib.pyplot as plt
import zipfile
import pandas as pd


class DownloadImagery: 

    def search_landast(lat, long, start_date, end_date, dataset='landsat_tm_c2_l2', max_cloud_cover=15):

        """
        Returns a list of satellite imagery and dates from Earth Explorer.

        Arguments:
            lat {float} -- Latitude value
            long {float} -- Longitude value
            start_date {datetime} -- Start date for the API start searching. Eg.: 1985-01-01
            end_date {datetime} -- End date for the API start searching. Eg.: 1985-01-01
            dataset {str} -- Satellite dataset of your choice. Default is landsat_tm_c2_l2
            max_cloud_cover {int} -- Percentage of desired clouds in the scene. Default is 15%

        Returns:
            GeoDataFrame -- A GeoDataFrame containing information about the found scenes.
        """


        # Initialize a new API instance and get an access key
        api = API(username_landsat, password_landsat)

        # Search for Landsat TM scenes
        scenes = api.search(
            dataset=dataset,
            latitude=lat,
            longitude=long,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=max_cloud_cover
        )

        found_scenes = len(scenes)
        print(f"{found_scenes} scenes found.")

        # Lista para armazenar os GeoDataFrames
        geo_dataframes = []

        for data_entry in scenes:
            # Criar o GeoDataFrame usando os dados do JSON
            gdf = gpd.GeoDataFrame([data_entry], geometry=[data_entry['spatial_coverage']])

            # Adicionar o GeoDataFrame à lista
            geo_dataframes.append(gdf)

        merged_gdf = gpd.GeoDataFrame(pd.concat(geo_dataframes, ignore_index=True))

        return merged_gdf

    def download_landsat(username, password, output_dir, id):

        """
        Downloads the first image from the list generated in the search_landast function.

        Arguments:
            username {str} -- EarthExplorer username.
            password {str} -- EarthExplorer password.
            output_dir {str} -- Path to the folder where the file will be saved.
            id {str} -- ID of the satellite image to be downloaded.

        """

        ee = EarthExplorer(username, password)

        ee.download(id, output_dir = output_dir)
        ee.logout()
        path = os.path.join(os.getcwd(), output_dir)

        # Removing files that are not the zipped satellite image.
        print('Removing old satellite images...')
        for root, dirs, files in os.walk(path):
            for file in files:
                if not file.endswith('.tar'):
                    os.remove(os.path.join(path, file))

        # Unzipping all satellite images from the tar folder.
        print('Unzipping images')
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('.tar'):
                    landsat = os.path.join(path, file)
                    tar = tarfile.open(landsat)
                    tar.extractall(output_dir)
                    tar.close()
                    os.remove(landsat)

    def search_sentinel(username, password, boundary, start_date, end_date, max_cloud_cover = 15):

        """
        Searches for Sentinel satellite imagery within a specified boundary.

        Arguments:
            username {str} -- Sentinel Hub username.
            password {str} -- Sentinel Hub password.
            boundary {GeoDataFrame} -- GeoDataFrame representing the boundary for the search area.
            start_date {datetime} -- Start date for the search.
            end_date {datetime} -- End date for the search.
            max_cloud_cover {int} -- Maximum cloud cover percentage. Default is 15%.

        Returns:
            GeoDataFrame -- A GeoDataFrame containing information about the found Sentinel scenes.

        """

        
        geom = boundary['geometry'].iloc[0]

        api = SentinelAPI(username,
                        password,
                        'https://scihub.copernicus.eu/dhus')
        
        products = api.query(geom,
                            date = (start_date, end_date),
                            platformname = 'Sentinel-2',
                            processinglevel = 'Level-2A',
                            cloudcoverpercentage = (0, max_cloud_cover)
                            )

        gdf = api.to_geodataframe(products)
        gdf_sorted = gdf.sort_values(by='ingestiondate')

        # filter results to show results that fully contain our desired boundary
        polya = boundary['geometry'].iloc[0]
        gdf_sorted['contains'] = gdf_sorted['geometry'].apply(lambda x:x.contains(polya))
        gdf_sorted = gdf_sorted[gdf_sorted['contains']==True]

        return gdf_sorted
    
    def download_sentinel(username, password, gdf, idx, bound_crs):
        """
            Downloads a Sentinel satellite image from the provided GeoDataFrame.

            Arguments:
                username {str} -- Sentinel Hub username.
                password {str} -- Sentinel Hub password.
                gdf {GeoDataFrame} -- GeoDataFrame containing information about the Sentinel scenes.
                idx {int} -- Index of the scene to be downloaded.
                bound_crs {str} -- Coordinate reference system (CRS) for the boundary.

            """
        api = SentinelAPI(username, password, 'https://scihub.copernicus.eu/dhus')
        meta = api.download(gdf.index[idx])
        #folder_path_title = meta['title']

        folder_path = os.getcwd()
        output_dir = os.path.join(folder_path, 'extracted')

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Unzipping the satellite image from the zip folder.
        print('Unzipping images')
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.endswith('.zip'):
                    sentinel_zip = os.path.join(folder_path, file)
                    with zipfile.ZipFile(sentinel_zip, 'r') as zip_ref:
                        zip_ref.extractall(output_dir)
                    os.remove(sentinel_zip)
        print('Unzipping completed.')
  

    def create_square_bbox(geometry):
        """
        Creates a square bounding box around the given geometry.

        Arguments:
            geometry {GeoSeries} -- GeoSeries representing the geometry.

        Returns:
            GeoDataFrame -- A GeoDataFrame containing the square bounding box.

        """

        #from shapely.geometry import Polygon
        # Get the bounds of the geometry column
        bounds = geometry.bounds
        
        # Extract the minimum and maximum values
        min_x = bounds["minx"].min()
        min_y = bounds["miny"].min()
        max_x = bounds["maxx"].max()
        max_y = bounds["maxy"].max()
        
        # Calculate the side length of the square
        side_length = max(max_x - min_x, max_y - min_y)
        
        # Calculate the coordinates of the square
        square_min_x = (max_x + min_x) / 2 - side_length / 2
        square_min_y = (max_y + min_y) / 2 - side_length / 2
        
        # Create a polygon representing the square bounding box
        bbox_polygon = Polygon([
            (square_min_x, square_min_y),
            (square_min_x, square_min_y + side_length),
            (square_min_x + side_length, square_min_y + side_length),
            (square_min_x + side_length, square_min_y)
        ])
        
        # Create a GeoDataFrame with the bounding box polygon
        bbox_gdf = gpd.GeoDataFrame(geometry=[bbox_polygon])
        
        return bbox_gdf

    def normalize(band):

        """
        Normalizes a raster band.

        Arguments:
            band {numpy array} -- The raster band to be normalized.

        Returns:
            numpy array -- The normalized raster band.

        """

        band_min, band_max = (band.min(), band.max())
        return ((band - band_min)/((band_max - band_min)))