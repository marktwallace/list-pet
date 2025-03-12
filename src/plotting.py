import plotly.express as px
import streamlit as st
from typing import Dict, Any, Tuple, Optional
import pandas as pd
import traceback
from src.message_manager import get_message_manager

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
        # Log plot specification for debugging purposes
        print(f"DEBUG - Plot spec received: {plot_spec}")
        
        # Check if dataframe is None or empty
        if df is None:
            error_message = "No data available for plotting. Try running a SELECT query first to retrieve data."
            print(f"ERROR - {error_message}")
            return None, error_message
            
        # Now it's safe to access df.columns
        print(f"DEBUG - DataFrame columns: {df.columns.tolist()}")
        print(f"DEBUG - DataFrame sample: {df.head().to_dict()}")
        
        plot_type = plot_spec.get('type')
        if plot_type not in self.plot_types:
            available_types = list(self.plot_types.keys())
            error_message = f"Invalid plot type: '{plot_type}'. Please use one of the supported types: {', '.join(available_types)}"
            print(f"ERROR - {error_message}")
            return None, error_message

        # Pre-process parameters to ensure correct types
        try:
            # Convert numeric parameters to the correct type
            if 'hole' in plot_spec:
                try:
                    plot_spec['hole'] = float(plot_spec['hole'])
                    if not (0 <= plot_spec['hole'] <= 1):
                        error_message = f"The 'hole' parameter must be between 0 and 1, got: {plot_spec['hole']}. Please provide a value between 0 and 1."
                        print(f"ERROR - {error_message}")
                        return None, error_message
                except ValueError:
                    error_message = f"The 'hole' parameter must be a number between 0 and 1, got: '{plot_spec['hole']}'. Please provide a numeric value."
                    print(f"ERROR - {error_message}")
                    return None, error_message
        except Exception as e:
            error_message = f"Error pre-processing plot parameters: {str(e)}. Please check your plot specification."
            print(f"ERROR - {error_message}")
            print(f"ERROR - Detailed error: {traceback.format_exc()}")
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
                missing_params = []
                if not names: missing_params.append('names')
                if not values: missing_params.append('values')
                
                error_message = f"Pie charts require 'names' and 'values' parameters. Missing: {', '.join(missing_params)}"
                print(f"ERROR - {error_message}")
                return None, error_message
                
            # Check if required fields are present in the DataFrame
            required_columns = [names, values]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                error_message = f"Missing required columns in DataFrame: {', '.join(missing_columns)}. Available columns are: {', '.join(df.columns.tolist())}"
                print(f"ERROR - {error_message}")
                return None, error_message
                
            plot_params['names'] = names
            plot_params['values'] = values
            
            print(f"DEBUG - Using pie chart parameters: names={names}, values={values}")
            
            # For pie charts, we need to make sure the values are numeric
            try:
                # Convert values column to numeric if it's not already
                df[values] = pd.to_numeric(df[values], errors='coerce')
                # Check if we have any non-NaN values
                if df[values].isna().all():
                    error_message = f"Values column '{values}' could not be converted to numeric type. Please ensure this column contains numeric data."
                    print(f"ERROR - {error_message}")
                    return None, error_message
            except Exception as e:
                error_message = f"Error converting values to numeric: {str(e)}. Please ensure the values column contains valid numeric data."
                print(f"ERROR - {error_message}")
                print(f"ERROR - Detailed error: {traceback.format_exc()}")
                return None, error_message
        else:
            # Standard charts use 'x' and 'y'
            x = plot_spec.get('x')
            y = plot_spec.get('y')
            
            # Check if required fields are present
            if not x or not y:
                missing_params = []
                if not x: missing_params.append('x')
                if not y: missing_params.append('y')
                
                error_message = f"{plot_type} charts require 'x' and 'y' parameters. Missing: {', '.join(missing_params)}"
                print(f"ERROR - {error_message}")
                return None, error_message
                
            # Check if required fields are present in the DataFrame
            required_columns = [x, y]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                error_message = f"Missing required columns in DataFrame: {', '.join(missing_columns)}. Available columns are: {', '.join(df.columns.tolist())}"
                print(f"ERROR - {error_message}")
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
                        print(f"WARNING - Could not parse hover_data: {plot_spec[param]}. Using default hover behavior.")
                        continue  # Skip adding hover_data if parsing fails
                else:
                    plot_params[param] = plot_spec[param]
        
        print(f"DEBUG - Final plot parameters: {plot_params}")
        
        # Create the plot
        try:
            fig = self.plot_types[plot_type](**plot_params)
            print("DEBUG - Plot created successfully")
            return fig, None
        except Exception as e:
            # This is a recoverable error - the user can fix their plot specification
            error_message = f"Error creating plot: {str(e)}"
            print(f"ERROR - {error_message}")
            print(f"ERROR - Plot creation traceback: {traceback.format_exc()}")
            
            # Provide more specific guidance based on the error type
            if "hole" in str(e) and "property" in str(e):
                error_message = "The 'hole' parameter must be a number between 0 and 1. Please update your plot specification to use a numeric value instead of a string."
            elif "Invalid value" in str(e) and "color" in str(e):
                error_message += "\n\nThe 'color' parameter might be invalid. Make sure it refers to a column in your data."
            elif "Invalid value" in str(e) and "x" in str(e):
                error_message += "\n\nThe 'x' parameter might be invalid. Check that it refers to a valid column in your data."
            elif "Invalid value" in str(e) and "y" in str(e):
                error_message += "\n\nThe 'y' parameter might be invalid. Check that it refers to a valid column in your data."
            elif "not found" in str(e).lower() or "missing" in str(e).lower():
                error_message += "\n\nOne or more required parameters are missing or invalid. Check the column names in your data."
            elif "could not convert" in str(e).lower() or "numeric" in str(e).lower():
                error_message += "\n\nOne of your columns could not be converted to a numeric type. For charts like bar, line, and scatter, both x and y values typically need to be numeric."
            else:
                error_message += "\n\nPlease check your plot specification and try again with valid parameters."
            
            return None, error_message
