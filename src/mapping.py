import plotly.express as px
import streamlit as st
from typing import Dict, Any, Tuple, Optional, List
import pandas as pd
import json
from src.metadata_manager import get_metadata_manager
from src.database import get_database

@st.cache_resource
def get_mapper():
    """Get or create mapper instance"""
    return Mapper()

class Mapper:
    def __init__(self):
        """Initialize the mapper with supported map types and styles."""
        # Map types supported by plotly express
        self.map_types = {
            'scatter_mapbox': px.scatter_mapbox,
            'line_mapbox': px.line_mapbox,
            'choropleth_mapbox': px.choropleth_mapbox,
            'density_mapbox': px.density_mapbox,
            'choropleth': px.choropleth
        }
        
        # Default mapbox style
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
        
        # Initialize metadata manager
        self.metadata_manager = get_metadata_manager()
        self.metadata_manager.initialize_metadata_tables()
    
    def calculate_optimal_zoom(self, df: pd.DataFrame, lat_col: str, lon_col: str) -> float:
        """
        Calculate the optimal zoom level to ensure all points are visible.
        
        Args:
            df: DataFrame containing the data points
            lat_col: Name of the latitude column
            lon_col: Name of the longitude column
            
        Returns:
            Optimal zoom level as a float
        """
        if df.empty or lat_col not in df.columns or lon_col not in df.columns:
            # Default to zoom level 1 (continental view) if data is invalid
            return 1.0
            
        # Get min/max lat/lon
        min_lat = df[lat_col].min()
        max_lat = df[lat_col].max()
        min_lon = df[lon_col].min()
        max_lon = df[lon_col].max()
        
        # Calculate the range
        lat_range = max_lat - min_lat
        lon_range = max_lon - min_lon
        
        # Handle case where all points are at the same location
        if lat_range == 0 and lon_range == 0:
            return 10.0  # City-level zoom for a single point
            
        # Calculate zoom based on the larger of the two ranges
        # These values are approximate and may need adjustment
        if max(lat_range, lon_range) > 90:  # Global view
            return 1
        elif max(lat_range, lon_range) > 45:  # Continental view
            return 2
        elif max(lat_range, lon_range) > 20:  # Large country view
            return 3
        elif max(lat_range, lon_range) > 10:  # Country view
            return 4
        elif max(lat_range, lon_range) > 5:  # Region view
            return 5
        elif max(lat_range, lon_range) > 2:  # State/province view
            return 6
        elif max(lat_range, lon_range) > 1:  # Metropolitan area
            return 7
        elif max(lat_range, lon_range) > 0.5:  # City view
            return 8
        elif max(lat_range, lon_range) > 0.1:  # District view
            return 9
        else:  # Neighborhood view
            return 10
            
        # Note: These zoom levels are approximations and may need fine-tuning
    
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
            geojson_source = map_spec.get('geojson')
            locations = map_spec.get('locations')
            featureidkey = map_spec.get('featureidkey')
            color = map_spec.get('color')
            
            # Check if required fields are present
            if not geojson_source or not locations or not color:
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
                # First, check if geojson_source is a known source ID in metadata
                source_metadata = self.metadata_manager.get_geojson_source(geojson_source)
                
                if source_metadata:
                    # Use metadata to get file path and feature ID property
                    geojson_path = source_metadata['file_path']
                    if not featureidkey:
                        featureidkey = source_metadata['feature_id_property']
                else:
                    # Assume geojson_source is a direct file path
                    geojson_path = geojson_source
                    if not featureidkey:
                        featureidkey = 'id'  # Default if not specified
                
                # Load the GeoJSON file
                with open(geojson_path, 'r') as f:
                    geojson_data = json.load(f)
                
                map_params['geojson'] = geojson_data
                map_params['locations'] = locations
                map_params['color'] = color
                
                # Handle featureidkey format
                if not featureidkey.startswith('properties.') and not featureidkey.startswith('id'):
                    featureidkey = f'properties.{featureidkey}'
                map_params['featureidkey'] = featureidkey
                
            except Exception as e:
                error_message = f"Error loading GeoJSON file: {str(e)}"
                print("DEBUG -", error_message)
                return None, error_message
        
        # Add optional parameters if present
        for param in ['title', 'color', 'size', 'hover_data', 'zoom', 'center', 'mapbox_style', 
                      'color_continuous_scale', 'range_color', 'opacity', 'labels', 'animation_frame',
                      'text', 'marker_color']:
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
                # Convert numeric parameters from strings to numbers
                elif param in ['zoom', 'opacity', 'size'] and isinstance(map_spec[param], str):
                    try:
                        map_params[param] = float(map_spec[param])
                        print(f"DEBUG - Converted {param} from string '{map_spec[param]}' to number {map_params[param]}")
                    except ValueError:
                        print(f"DEBUG - Could not convert {param} value to number: {map_spec[param]}, using default")
                        # Don't add the parameter, let Plotly use its default
                        continue
                else:
                    map_params[param] = map_spec[param]
        
        # Set default mapbox style if not provided
        if map_type in ['scatter_mapbox', 'line_mapbox', 'choropleth_mapbox', 'density_mapbox'] and 'mapbox_style' not in map_params:
            map_params['mapbox_style'] = self.default_mapbox_style
        
        # Always calculate and use optimal zoom level for scatter_mapbox maps
        if map_type == 'scatter_mapbox' and 'lat' in map_params and 'lon' in map_params:
            lat_col = map_params['lat']
            lon_col = map_params['lon']
            optimal_zoom = self.calculate_optimal_zoom(df, lat_col, lon_col)
            
            # If a zoom was provided, log that we're overriding it
            if 'zoom' in map_params:
                provided_zoom = map_params['zoom']
                print(f"DEBUG - Overriding provided zoom level {provided_zoom} with calculated optimal zoom: {optimal_zoom}")
            else:
                print(f"DEBUG - Using calculated optimal zoom level: {optimal_zoom}")
                
            map_params['zoom'] = optimal_zoom
        
        # Store marker_color if provided, but remove it from map_params as it's not a valid parameter for px.scatter_mapbox
        marker_color = None
        if 'marker_color' in map_params:
            marker_color = map_params.pop('marker_color')
            print(f"DEBUG - Extracted marker_color: {marker_color} (will be applied after map creation)")
        
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
            
            # Apply marker_color if it was provided
            if map_type == 'scatter_mapbox' and marker_color:
                print(f"DEBUG - Applying marker_color: {marker_color}")
                fig.update_traces(marker=dict(color=marker_color))
            
            return fig, None
        except Exception as e:
            error_message = f"Error creating map: {str(e)}"
            print("DEBUG -", error_message)
            import traceback
            print(f"DEBUG - Map creation traceback: {traceback.format_exc()}")
            return None, error_message
            
    def list_available_geojson_sources(self) -> List[Dict[str, Any]]:
        """List all available GeoJSON sources from metadata"""
        return self.metadata_manager.list_geojson_sources()
        
    def get_geojson_source_info(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a GeoJSON source"""
        source = self.metadata_manager.get_geojson_source(source_id)
        if not source:
            return None
            
        # Add properties information
        properties = self.metadata_manager.get_geojson_properties(source_id)
        source['properties'] = properties
        
        return source 