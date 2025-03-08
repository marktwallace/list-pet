import plotly.express as px
import streamlit as st
from typing import Dict, Any, Tuple, Optional
import pandas as pd
import json

@st.cache_resource
def get_mapper():
    """Get or create mapper instance"""
    return Mapper()

class Mapper:
    def __init__(self):
        self.map_types = {
            'scatter_mapbox': px.scatter_mapbox,
            'line_mapbox': px.line_mapbox,
            'choropleth_mapbox': px.choropleth_mapbox,
            'density_mapbox': px.density_mapbox,
            'choropleth': px.choropleth
        }
        
        # Default mapbox style if not specified
        self.default_mapbox_style = "open-street-map"
        
        # Common map center points
        self.default_center = {"lat": 0, "lon": 0}
        self.common_centers = {
            "us": {"lat": 39.8283, "lon": -98.5795},
            "europe": {"lat": 54.5260, "lon": 15.2551},
            "asia": {"lat": 34.0479, "lon": 100.6197},
            "africa": {"lat": 8.7832, "lon": 34.5085},
            "australia": {"lat": -25.2744, "lon": 133.7751},
            "south_america": {"lat": -8.7832, "lon": -55.4915}
        }
    
    def create_map(self, map_spec: Dict[str, Any], df: Any) -> Tuple[Optional[Any], Optional[str]]:
        """
        Create a map based on the specification and return a tuple:
        (fig, error_message). If mapping succeeds, error_message is None;
        otherwise, fig is None.
        """
        # Debug logging
        print("DEBUG - Map spec received:", map_spec)
        
        # Check if dataframe is None or empty
        if df is None:
            error_message = "Cannot create map: No data available"
            print("DEBUG -", error_message)
            return None, error_message
            
        # Now it's safe to access df.columns
        print("DEBUG - DataFrame columns:", df.columns.tolist())
        print("DEBUG - DataFrame sample:", df.head().to_dict())
        
        map_type = map_spec.get('type')
        if map_type not in self.map_types:
            error_message = f"Unknown map type: {map_type}. Available types: {list(self.map_types.keys())}"
            print("DEBUG -", error_message)
            return None, error_message

        # Build map parameters
        map_params = {
            'data_frame': df,
        }
        
        # Handle different parameter requirements for different map types
        if map_type in ['scatter_mapbox', 'line_mapbox', 'density_mapbox']:
            # These map types require lat and lon
            lat = map_spec.get('lat')
            lon = map_spec.get('lon')
            
            # Check if required fields are present
            if not lat or not lon:
                error_message = f"{map_type} maps require 'lat' and 'lon' parameters"
                print("DEBUG -", error_message)
                return None, error_message
                
            # Check if required fields are present in the DataFrame
            required_columns = [lat, lon]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                error_message = f"Missing required columns in DataFrame: {', '.join(missing_columns)}"
                print("DEBUG -", error_message)
                return None, error_message
                
            map_params['lat'] = lat
            map_params['lon'] = lon
            
        elif map_type == 'choropleth_mapbox' or map_type == 'choropleth':
            # These map types require geojson and locations
            geojson_path = map_spec.get('geojson')
            locations = map_spec.get('locations')
            featureidkey = map_spec.get('featureidkey', 'id')
            color = map_spec.get('color')
            
            # Check if required fields are present
            if not geojson_path or not locations or not color:
                error_message = f"{map_type} maps require 'geojson', 'locations', and 'color' parameters"
                print("DEBUG -", error_message)
                return None, error_message
                
            # Check if required fields are present in the DataFrame
            required_columns = [locations, color]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                error_message = f"Missing required columns in DataFrame: {', '.join(missing_columns)}"
                print("DEBUG -", error_message)
                return None, error_message
            
            # Try to load the GeoJSON file
            try:
                with open(geojson_path, 'r') as f:
                    geojson_data = json.load(f)
                map_params['geojson'] = geojson_data
                map_params['locations'] = locations
                map_params['color'] = color
                map_params['featureidkey'] = featureidkey
            except Exception as e:
                error_message = f"Error loading GeoJSON file: {str(e)}"
                print("DEBUG -", error_message)
                return None, error_message
        
        # Add optional parameters if present
        for param in ['title', 'color', 'size', 'hover_data', 'zoom', 'center', 'mapbox_style', 
                      'color_continuous_scale', 'range_color', 'opacity', 'labels', 'animation_frame']:
            if param in map_spec:
                # Handle special cases
                if param == 'hover_data' and isinstance(map_spec[param], str):
                    try:
                        map_params[param] = [col.strip() for col in map_spec[param].split(',')]
                    except Exception:
                        print(f"DEBUG - Could not parse hover_data: {map_spec[param]}")
                        continue
                elif param == 'center' and isinstance(map_spec[param], str):
                    # Handle named centers
                    center_name = map_spec[param].lower()
                    if center_name in self.common_centers:
                        map_params[param] = self.common_centers[center_name]
                    else:
                        print(f"DEBUG - Unknown center name: {center_name}, using default")
                        map_params[param] = self.default_center
                else:
                    map_params[param] = map_spec[param]
        
        # Set default mapbox style if not provided
        if map_type in ['scatter_mapbox', 'line_mapbox', 'choropleth_mapbox', 'density_mapbox'] and 'mapbox_style' not in map_params:
            map_params['mapbox_style'] = self.default_mapbox_style
        
        print("DEBUG - Final map parameters:", map_params)
        
        # Create the map
        try:
            fig = self.map_types[map_type](**map_params)
            print("DEBUG - Map created successfully")
            
            # Update layout for better appearance
            fig.update_layout(
                margin={"r": 0, "t": 30, "l": 0, "b": 0},
                height=600
            )
            
            return fig, None
        except Exception as e:
            error_message = f"Error creating map: {str(e)}"
            print("DEBUG -", error_message)
            import traceback
            print(f"DEBUG - Map creation traceback: {traceback.format_exc()}")
            return None, error_message 