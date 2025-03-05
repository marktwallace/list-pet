import plotly.express as px
import streamlit as st
from typing import Dict, List, Any

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
    
    def create_plot(self, plot_spec: Dict[str, Any], df: Any) -> None:
        """Create and display a plot based on specification"""
        # Debug logging
        print("DEBUG - Plot spec received:", plot_spec)
        print("DEBUG - DataFrame columns:", df.columns.tolist())
        
        plot_type = plot_spec.get('type')
        if plot_type not in self.plot_types:
            print("DEBUG - Available plot types:", list(self.plot_types.keys()))
            st.error(f"Unknown plot type: {plot_type}")
            return
            
        # Extract required fields
        x = plot_spec.get('x')
        y = plot_spec.get('y')
        if not (x and y):
            print(f"DEBUG - Missing required fields. Got x={x}, y={y}")
            st.error(f"Missing required x or y field. Got x={x}, y={y}")
            return
            
        # Build plot parameters
        plot_params = {
            'data_frame': df,
            'x': x,
            'y': y
        }
        
        # Add optional parameters if present
        for param in ['title', 'color', 'size', 'hover_data', 'facet']:
            if param in plot_spec:
                # Handle hover_data specially as it might be a string representation of a list
                if param == 'hover_data' and isinstance(plot_spec[param], str):
                    try:
                        plot_params[param] = eval(plot_spec[param])
                    except:
                        print(f"DEBUG - Could not parse hover_data: {plot_spec[param]}")
                        st.warning(f"Could not parse hover_data: {plot_spec[param]}")
                        continue
                else:
                    plot_params[param] = plot_spec[param]
        
        print("DEBUG - Final plot parameters:", plot_params)
        # Create and display the plot
        fig = self.plot_types[plot_type](**plot_params)
        st.plotly_chart(fig, use_container_width=True)