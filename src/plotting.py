import plotly.express as px
import streamlit as st
from typing import Dict, Any, Tuple, Optional
import pandas as pd

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
        
        # Check if dataframe is None or empty
        if df is None:
            error_message = "Cannot create plot: No data available"
            print("DEBUG -", error_message)
            return None, error_message
            
        # Now it's safe to access df.columns
        print("DEBUG - DataFrame columns:", df.columns.tolist())
        print("DEBUG - DataFrame sample:", df.head().to_dict())
        
        plot_type = plot_spec.get('type')
        if plot_type not in self.plot_types:
            error_message = f"Unknown plot type: {plot_type}. Available types: {list(self.plot_types.keys())}"
            print("DEBUG -", error_message)
            return None, error_message

        # Pre-process parameters to ensure correct types
        try:
            # Convert numeric parameters to the correct type
            if 'hole' in plot_spec:
                try:
                    plot_spec['hole'] = float(plot_spec['hole'])
                    if not (0 <= plot_spec['hole'] <= 1):
                        error_message = f"The 'hole' parameter must be between 0 and 1, got: {plot_spec['hole']}"
                        print("DEBUG -", error_message)
                        return None, error_message
                except ValueError:
                    error_message = f"The 'hole' parameter must be a number between 0 and 1, got: '{plot_spec['hole']}'"
                    print("DEBUG -", error_message)
                    return None, error_message
        except Exception as e:
            error_message = f"Error pre-processing plot parameters: {str(e)}"
            print("DEBUG -", error_message)
            return None, error_message

        # Build plot parameters
        plot_params = {
            'data_frame': df,
        }
        
        # Handle different parameter requirements for different plot types
        if plot_type == 'pie':
            # Pie charts use 'names' and 'values' instead of 'x' and 'y'
            names = plot_spec.get('names')
            values = plot_spec.get('values')
            
            # Check if required fields are present
            if not names or not values:
                error_message = f"Pie charts require 'names' and 'values' parameters"
                print("DEBUG -", error_message)
                return None, error_message
                
            # Check if required fields are present in the DataFrame
            required_columns = [names, values]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                error_message = f"Missing required columns in DataFrame: {', '.join(missing_columns)}"
                print("DEBUG -", error_message)
                return None, error_message
                
            plot_params['names'] = names
            plot_params['values'] = values
            
            print("DEBUG - Using pie chart parameters: names={}, values={}".format(names, values))
            
            # For pie charts, we need to make sure the values are numeric
            try:
                # Convert values column to numeric if it's not already
                df[values] = pd.to_numeric(df[values], errors='coerce')
                # Check if we have any non-NaN values
                if df[values].isna().all():
                    error_message = f"Values column '{values}' could not be converted to numeric type"
                    print("DEBUG -", error_message)
                    return None, error_message
            except Exception as e:
                error_message = f"Error converting values to numeric: {str(e)}"
                print("DEBUG -", error_message)
                return None, error_message
        else:
            # Standard charts use 'x' and 'y'
            x = plot_spec.get('x')
            y = plot_spec.get('y')
            
            # Check if required fields are present
            if not x or not y:
                error_message = f"Standard charts require 'x' and 'y' parameters"
                print("DEBUG -", error_message)
                return None, error_message
                
            # Check if required fields are present in the DataFrame
            required_columns = [x, y]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                error_message = f"Missing required columns in DataFrame: {', '.join(missing_columns)}"
                print("DEBUG -", error_message)
                return None, error_message
                
            plot_params['x'] = x
            plot_params['y'] = y
        
        # Add optional parameters if present
        for param in ['title', 'color', 'size', 'hover_data', 'facet', 'hole']:
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
            print("DEBUG - Plot created successfully")
            return fig, None
        except Exception as e:
            error_message = f"Error creating plot: {str(e)}"
            print("DEBUG -", error_message)
            import traceback
            print(f"DEBUG - Plot creation traceback: {traceback.format_exc()}")
            
            # Provide more specific error messages for common issues
            if "hole" in str(e) and "property" in str(e):
                error_message = "The 'hole' parameter must be a number between 0 and 1. Please update your plot specification to use a numeric value instead of a string."
            
            return None, error_message
