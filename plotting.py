import plotly.express as px
import streamlit as st
from typing import Dict, Any, Tuple, Optional

@st.cache_resource
def get_plotter():
    """Get or create plotter instance"""
    return Plotter()

class Plotter:
    def __init__(self):
        self.plot_types = {
            'bar': px.bar,
            'box': px.box,
            'line': px.line,
            'scatter': px.scatter,
            'histogram': px.histogram,
            'pie': px.pie
        }
    
    def create_plot(self, plot_spec: Dict[str, Any], df: Any) -> Tuple[Optional[Any], Optional[str]]:
        """
        Create a plot based on the specification and return a tuple:
        (fig, error_message). If plotting succeeds, error_message is None;
        otherwise, fig is None.
        """
        # Debug logging
        print("DEBUG - Plot spec received:", plot_spec)
        print("DEBUG - DataFrame columns:", df.columns.tolist())
        
        plot_type = plot_spec.get('type')
        if plot_type not in self.plot_types:
            error_message = f"Unknown plot type: {plot_type}. Available types: {list(self.plot_types.keys())}"
            print("DEBUG -", error_message)
            return None, error_message

        # Extract required fields
        x = plot_spec.get('x')
        y = plot_spec.get('y')
        
        # Check if required fields are present in the DataFrame
        required_columns = [x, y]
        if 'hover_data' in plot_spec:
            hover_data_value = plot_spec['hover_data']
            if isinstance(hover_data_value, list):
                required_columns.extend(hover_data_value)
            elif isinstance(hover_data_value, str):
                try:
                    hover_data_list = eval(hover_data_value)
                    if isinstance(hover_data_list, list):
                        required_columns.extend(hover_data_list)
                except Exception:
                    error_message = f"Could not parse hover_data: {hover_data_value}"
                    print("DEBUG -", error_message)
                    return None, error_message

        # Check for missing columns
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            error_message = f"Missing required columns in DataFrame: {', '.join(missing_columns)}"
            print("DEBUG -", error_message)
            return None, error_message

        # Build plot parameters
        plot_params = {
            'data_frame': df,
            'x': x,
            'y': y
        }
        
        # Add optional parameters if present
        for param in ['title', 'color', 'size', 'hover_data', 'facet']:
            if param in plot_spec:
                if param == 'hover_data' and isinstance(plot_spec[param], str):
                    try:
                        plot_params[param] = eval(plot_spec[param])
                    except Exception:
                        print(f"DEBUG - Could not parse hover_data: {plot_spec[param]}")
                        continue  # Skip adding hover_data if parsing fails
                else:
                    plot_params[param] = plot_spec[param]
        
        print("DEBUG - Final plot parameters:", plot_params)
        
        # Create the plot
        try:
            fig = self.plot_types[plot_type](**plot_params)
            return fig, None
        except Exception as e:
            error_message = f"Error creating plot: {str(e)}"
            print("DEBUG -", error_message)
            return None, error_message
