"""
Chart Renderer Module

This module provides functionality to render Plotly charts based on parameters
extracted from <chart> elements in the List Pet application.

It supports various chart types including:
- Standard charts: bar, box, line, scatter, histogram
- Pie charts: pie (with optional hole for donut charts)
- Map charts: scatter_mapbox, line_mapbox, choropleth_mapbox, density_mapbox, choropleth

Usage:
    from chart_renderer import render_chart
    
    # Create a DataFrame
    df = pd.DataFrame({'category': ['A', 'B', 'C'], 'value': [10, 20, 30]})
    
    # Define chart parameters
    chart_content = '''
    type: bar
    x: category
    y: value
    title: My Chart
    '''
    
    # Render the chart
    fig, err = render_chart(df, chart_content)
    
    if err:
        print(f"Error: {err}")
    else:
        # Display the chart in Streamlit
        st.plotly_chart(fig)
        
        # Or save to HTML
        fig.write_html("chart.html")
"""

import re
import json
import plotly.graph_objects as go
import numpy as np
import pandas as pd
from typing import Tuple, Dict, List, Any, Optional, Union


def render_chart(df: pd.DataFrame, content: str) -> Tuple[go.Figure, Optional[str]]:
    """
    Renders a chart based on the provided content string and dataframe.
    
    Args:
        df: The pandas DataFrame containing the data to plot
        content: A string containing chart configuration in YAML-like format
        
    Returns:
        A tuple containing (plotly figure, error message or None)
    """
    try:
        # Parse the chart configuration
        config = parse_chart_config(content)
        
        # Get the chart type
        chart_type = config.get('type', '').lower()
        
        # Create the appropriate chart based on the type
        if chart_type == 'bar':
            fig = create_bar_chart(df, config)
        elif chart_type == 'box':
            fig = create_box_chart(df, config)
        elif chart_type == 'line':
            fig = create_line_chart(df, config)
        elif chart_type == 'scatter':
            fig = create_scatter_chart(df, config)
        elif chart_type == 'histogram':
            fig = create_histogram_chart(df, config)
        elif chart_type == 'pie':
            fig = create_pie_chart(df, config)
        elif chart_type == 'scatter_mapbox':
            fig = create_scatter_mapbox(df, config)
        elif chart_type == 'line_mapbox':
            fig = create_line_mapbox(df, config)
        elif chart_type == 'choropleth_mapbox':
            fig = create_choropleth_mapbox(df, config)
        else:
            return None, f"Unsupported chart type: {chart_type}"
        
        # Apply common layout updates
        update_layout(fig, config)
        
        # Test if the figure can be converted to JSON (which is what Plotly does when rendering)
        # This will catch any Plotly-specific validation errors
        try:
            fig.to_json()
        except Exception as plotly_error:
            return None, f"Error rendering chart: {str(plotly_error)}"
            
        return fig, None
    except ValueError as ve:
        return None, str(ve)
    except KeyError as ke:
        return None, f"Missing key in configuration: {str(ke)}"
    except Exception as e:
        return None, f"Error rendering chart: {str(e)}"


def parse_chart_config(content: str) -> Dict[str, Any]:
    """
    Parses the YAML-like chart configuration string into a dictionary.
    
    Args:
        content: The chart configuration string
        
    Returns:
        A dictionary containing the chart configuration
    """
    config = {}
    
    # Print the raw content for debugging
    print(f"DEBUG - Raw chart config content:\n{content}")
    
    # Split the content into lines and process each line
    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line or ':' not in line:
            continue
            
        # Split the line into key and value
        key, value = [part.strip() for part in line.split(':', 1)]
        
        # Handle list values (comma-separated values enclosed in square brackets)
        if value.startswith('[') and value.endswith(']'):
            value = [item.strip() for item in value[1:-1].split(',')]
        
        config[key] = value
    
    # Print the parsed config for debugging
    print(f"DEBUG - Parsed chart config: {config}")
    return config


def get_hover_text(df: pd.DataFrame, config: Dict[str, Any]) -> List[str]:
    """
    Generates hover text based on the specified columns in the config.
    
    Args:
        df: The DataFrame containing the data
        config: The chart configuration dictionary
        
    Returns:
        A list of formatted hover text strings
    """
    if 'hovertext' not in config:
        return None
    
    # Parse the hovertext value into a list of column names
    if isinstance(config['hovertext'], str):
        columns = [col.strip() for col in config['hovertext'].split(',')]
    else:
        columns = config['hovertext']
    
    # Filter to only include columns that exist in the DataFrame
    valid_columns = [col for col in columns if col in df.columns]
    
    if not valid_columns:
        return None
    
    # Generate the hover text for each row
    hover_texts = []
    for _, row in df.iterrows():
        text_parts = []
        for col in valid_columns:
            text_parts.append(f"{col}: {row[col]}")
        hover_texts.append("<br>".join(text_parts))
    
    return hover_texts


def create_bar_chart(df: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
    """Creates a bar chart based on the provided configuration."""
    x = config.get('x')
    y = config.get('y')
    
    if not x or not y or x not in df.columns or y not in df.columns:
        raise ValueError(f"Invalid x or y field for bar chart: {x}, {y}")
    
    # Get marker color if specified
    marker_color = get_marker_color(df, config)
    
    # Create the figure
    fig = go.Figure(go.Bar(
        x=df[x],
        y=df[y],
        text=df[config['text']] if 'text' in config and config['text'] in df.columns else None,
        marker=dict(color=marker_color),
        hovertext=get_hover_text(df, config),
        hoverinfo='text' if 'hovertext' in config else None
    ))
    
    return fig


def create_box_chart(df: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
    """Creates a box chart based on the provided configuration."""
    x = config.get('x')
    y = config.get('y')
    
    if not y or y not in df.columns:
        raise ValueError(f"Invalid y field for box chart: {y}")
    
    # Get marker color if specified
    marker_color = get_marker_color(df, config)
    
    # Create the figure
    fig = go.Figure(go.Box(
        x=df[x] if x and x in df.columns else None,
        y=df[y],
        marker=dict(color=marker_color),
        hovertext=get_hover_text(df, config),
        hoverinfo='text' if 'hovertext' in config else None
    ))
    
    return fig


def create_line_chart(df: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
    """Creates a line chart based on the provided configuration."""
    x = config.get('x')
    y = config.get('y')
    
    if not x or not y or x not in df.columns or y not in df.columns:
        raise ValueError(f"Invalid x or y field for line chart: {x}, {y}")
    
    # Get marker color if specified
    marker_color = get_marker_color(df, config)
    
    # Create the figure
    fig = go.Figure(go.Scatter(
        x=df[x],
        y=df[y],
        mode='lines+markers',
        text=df[config['text']] if 'text' in config and config['text'] in df.columns else None,
        marker=dict(color=marker_color),
        hovertext=get_hover_text(df, config),
        hoverinfo='text' if 'hovertext' in config else None
    ))
    
    return fig


def create_scatter_chart(df: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
    """Creates a scatter chart based on the provided configuration."""
    x = config.get('x')
    y = config.get('y')
    
    if not x or not y or x not in df.columns or y not in df.columns:
        raise ValueError(f"Invalid x or y field for scatter chart: {x}, {y}")
    
    # Get marker color and size if specified
    marker_color = get_marker_color(df, config)
    marker_size = get_marker_size(df, config)
    
    # Create the figure
    fig = go.Figure(go.Scatter(
        x=df[x],
        y=df[y],
        mode='markers',
        text=df[config['text']] if 'text' in config and config['text'] in df.columns else None,
        marker=dict(
            color=marker_color,
            size=marker_size,
            sizemode='area',
            sizeref=2.*max(marker_size)/(40.**2) if marker_size is not None and not isinstance(marker_size, str) else None,
            sizemin=4
        ),
        hovertext=get_hover_text(df, config),
        hoverinfo='text' if 'hovertext' in config else None
    ))
    
    return fig


def create_histogram_chart(df: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
    """Creates a histogram chart based on the provided configuration."""
    x = config.get('x')
    
    if not x or x not in df.columns:
        raise ValueError(f"Invalid x field for histogram chart: {x}")
    
    # Get marker color if specified
    marker_color = get_marker_color(df, config)
    
    # Create the figure
    fig = go.Figure(go.Histogram(
        x=df[x],
        marker=dict(color=marker_color),
        hovertext=get_hover_text(df, config),
        hoverinfo='text' if 'hovertext' in config else None
    ))
    
    return fig


def create_pie_chart(df: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
    """Creates a pie chart based on the provided configuration."""
    labels = config.get('labels')
    values = config.get('values')
    
    if not labels or not values or labels not in df.columns or values not in df.columns:
        raise ValueError(f"Invalid labels or values field for pie chart: {labels}, {values}")
    
    # Create the figure
    fig = go.Figure(go.Pie(
        labels=df[labels],
        values=df[values],
        text=df[config['text']] if 'text' in config and config['text'] in df.columns else None,
        hovertext=get_hover_text(df, config),
        hoverinfo='text' if 'hovertext' in config else 'label+percent',
        hole=float(config['hole']) if 'hole' in config else 0
    ))
    
    return fig


def create_scatter_mapbox(df: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
    """Creates a scatter mapbox based on the provided configuration."""
    lat = config.get('lat')
    lon = config.get('lon')
    
    if not lat or not lon or lat not in df.columns or lon not in df.columns:
        raise ValueError(f"Invalid lat or lon field for scatter_mapbox: {lat}, {lon}")
    
    # Get marker color and size if specified
    marker_color = get_marker_color(df, config)
    marker_size = get_marker_size(df, config)
    
    # Get text field if specified
    text = df[config['text']] if 'text' in config and config['text'] in df.columns else None
    
    # Create the figure
    fig = go.Figure(go.Scattermapbox(
        lat=df[lat],
        lon=df[lon],
        mode='markers',
        text=text,
        marker=go.scattermapbox.Marker(
            size=marker_size,
            color=marker_color,
            colorscale='Viridis' if marker_color is not None and not isinstance(marker_color, str) else None,
            sizemode='area',
            sizeref=2.*max(marker_size)/(40.**2) if marker_size is not None and not isinstance(marker_size, str) else None,
            sizemin=4
        ),
        hovertext=get_hover_text(df, config),
        hoverinfo='text' if 'hovertext' in config else None
    ))
    
    # Configure mapbox
    mapbox_style = config.get('mapbox_style', 'open-street-map')
    zoom = float(config.get('zoom', 3))
    
    # Set center either by named region or by coordinates mean
    center = config.get('center')
    if center:
        # Predefined centers for common regions
        centers = {
            'us': {'lat': 39.8283, 'lon': -98.5795},
            'europe': {'lat': 54.5260, 'lon': 15.2551},
            'asia': {'lat': 34.0479, 'lon': 100.6197},
            'africa': {'lat': 8.7832, 'lon': 34.5085},
            'australia': {'lat': -25.2744, 'lon': 133.7751},
            'south_america': {'lat': -8.7832, 'lon': -55.4915}
        }
        center_coords = centers.get(center.lower(), {'lat': df[lat].mean(), 'lon': df[lon].mean()})
    else:
        center_coords = {'lat': df[lat].mean(), 'lon': df[lon].mean()}
    
    fig.update_layout(
        mapbox=dict(
            style=mapbox_style,
            zoom=zoom,
            center=center_coords
        ),
        margin={"r": 0, "t": 40, "l": 0, "b": 0}
    )
    
    return fig


def create_line_mapbox(df: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
    """Creates a line mapbox based on the provided configuration."""
    lat = config.get('lat')
    lon = config.get('lon')
    
    if not lat or not lon or lat not in df.columns or lon not in df.columns:
        raise ValueError(f"Invalid lat or lon field for line_mapbox: {lat}, {lon}")
    
    # Get marker color if specified
    marker_color = get_marker_color(df, config)
    
    # Create the figure
    fig = go.Figure(go.Scattermapbox(
        lat=df[lat],
        lon=df[lon],
        mode='lines+markers',
        marker=dict(color=marker_color),
        hovertext=get_hover_text(df, config),
        hoverinfo='text' if 'hovertext' in config else None
    ))
    
    # Configure mapbox
    mapbox_style = config.get('mapbox_style', 'open-street-map')
    zoom = float(config.get('zoom', 3))
    
    fig.update_layout(
        mapbox=dict(
            style=mapbox_style,
            zoom=zoom,
            center=dict(lat=df[lat].mean(), lon=df[lon].mean())
        ),
        margin={"r": 0, "t": 40, "l": 0, "b": 0}
    )
    
    return fig


def create_choropleth_mapbox(df: pd.DataFrame, config: Dict[str, Any]) -> go.Figure:
    """Creates a choropleth mapbox based on the provided configuration."""
    locations = config.get('locations')
    geojson = config.get('geojson')
    
    if not locations or not geojson or locations not in df.columns:
        raise ValueError(f"Invalid locations or geojson for choropleth_mapbox: {locations}, {geojson}")
    
    # Handle external GeoJSON file or object
    try:
        if isinstance(geojson, str) and (geojson.startswith('{') or geojson.startswith('[')):
            geojson_data = json.loads(geojson)
        elif isinstance(geojson, str) and (geojson.endswith('.json') or geojson.endswith('.geojson')):
            with open(geojson, 'r') as f:
                geojson_data = json.load(f)
        else:
            geojson_data = geojson
    except Exception as e:
        raise ValueError(f"Error loading GeoJSON: {str(e)}")
    
    # Get marker color and color scale if specified
    color = get_marker_color(df, config)
    color_scale = config.get('color_continuous_scale', 'Viridis')
    
    # Get range_color if specified
    range_color = None
    if 'range_color' in config:
        if isinstance(config['range_color'], str):
            range_parts = config['range_color'].strip('[]').split(',')
            range_color = [float(part.strip()) for part in range_parts]
        else:
            range_color = config['range_color']
    
    # Get featureidkey if specified
    featureidkey = config.get('featureidkey', 'id')
    if not featureidkey.startswith('properties.') and featureidkey != 'id':
        featureidkey = f"properties.{featureidkey}"
    
    # Get opacity if specified
    opacity = float(config.get('opacity', 0.8))
    
    # Create the figure
    fig = go.Figure(go.Choroplethmapbox(
        geojson=geojson_data,
        locations=df[locations],
        z=color,
        colorscale=color_scale,
        marker_opacity=opacity,
        marker_line_width=0,
        colorbar=dict(thickness=20, title=locations),
        zmin=range_color[0] if range_color else None,
        zmax=range_color[1] if range_color and len(range_color) > 1 else None,
        featureidkey=featureidkey,
        hovertext=get_hover_text(df, config),
        hoverinfo='text' if 'hovertext' in config else None
    ))
    
    # Configure mapbox
    mapbox_style = config.get('mapbox_style', 'open-street-map')
    zoom = float(config.get('zoom', 3))
    
    fig.update_layout(
        mapbox=dict(
            style=mapbox_style,
            zoom=zoom,
            center=dict(lat=0, lon=0)  # Default center, will be adjusted by the map
        ),
        margin={"r": 0, "t": 40, "l": 0, "b": 0}
    )
    
    return fig


def get_marker_color(df: pd.DataFrame, config: Dict[str, Any]) -> Union[str, None]:
    """
    Gets the marker color from the configuration.
    
    Args:
        df: The DataFrame containing the data
        config: The chart configuration dictionary
        
    Returns:
        Either a valid color string or None
    """
    if 'marker_color' not in config:
        return None
    
    marker_color = config['marker_color']
    print(f"DEBUG - marker_color value: '{marker_color}' of type {type(marker_color)}")
    
    # For now, we only support constant color values
    # We specifically ignore any value that matches a column name
    # This is a temporary simplification until proper column mapping is implemented
    
    # Common color names that are safe to use
    valid_colors = [
        'red', 'blue', 'green', 'yellow', 'orange', 'purple', 'pink',
        'brown', 'black', 'white', 'gray', 'cyan', 'magenta'
    ]
    
    # If it's a common color name, return it
    if isinstance(marker_color, str) and marker_color.lower() in valid_colors:
        return marker_color
    
    # If it's a hex color code, return it
    if isinstance(marker_color, str) and marker_color.startswith('#'):
        return marker_color
        
    # Otherwise, return a default color
    return 'blue'


def get_marker_size(df: pd.DataFrame, config: Dict[str, Any]) -> Union[List, int, None]:
    """
    Gets the marker size from the configuration.
    
    Args:
        df: The DataFrame containing the data
        config: The chart configuration dictionary
        
    Returns:
        Either a column from the dataframe, a constant size, or None
    """
    if 'marker_size' not in config:
        return None
    
    marker_size = config['marker_size']
    if marker_size in df.columns:
        return df[marker_size]
    
    try:
        return int(marker_size)
    except (ValueError, TypeError):
        return None


def update_layout(fig: go.Figure, config: Dict[str, Any]) -> None:
    """
    Updates the figure layout with common configurations.
    
    Args:
        fig: The plotly figure to update
        config: The chart configuration dictionary
    """
    # Set title if specified
    if 'title' in config:
        fig.update_layout(title=config['title'])
    
    # Set axis labels if specified
    x_label = config.get('xlabel')
    y_label = config.get('ylabel')
    
    if x_label:
        fig.update_xaxes(title=x_label)
    if y_label:
        fig.update_yaxes(title=y_label)
    
    # Set general layout properties
    fig.update_layout(
        template='plotly',  # Use a clean template
        height=600,  # Default height
        margin=dict(l=50, r=50, t=50, b=50)
    ) 