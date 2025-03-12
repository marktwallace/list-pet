import json
from typing import Dict, List, Any, Tuple, Optional
import pandas as pd
import traceback

from .parse import parse_markup
from .sql_utils import execute_sql
from .database import Database
from .constants import USER_ROLE, DATABASE_ACTOR

def process_sql_blocks(parsed_response: Dict[str, Any], db: Database) -> Tuple[List[Dict[str, Any]], bool, Optional[pd.DataFrame]]:
    """
    Process SQL blocks from a parsed AI response.
    
    Args:
        parsed_response: The parsed AI response containing SQL blocks
        db: The database to execute queries against
        
    Returns:
        Tuple containing:
        - List of SQL result messages to be added to the conversation
        - Boolean indicating if any errors occurred
        - The last dataframe produced (if any)
    """
    messages = []
    last_df = None
    had_error = False
    
    for block in parsed_response.get("sql", []):
        if query := block.get("query"):
            result, is_error, df = execute_sql(query, db)
            sql_message = {"role": USER_ROLE, "content": f"{DATABASE_ACTOR}:\n{result}", "dataframe": df}
            messages.append(sql_message)
            had_error = had_error or is_error
            if df is not None:
                last_df = df
                print(f"DEBUG - SQL result dataframe: {df.shape}, columns: {df.columns.tolist()}")
            else:
                print(f"DEBUG - SQL query executed, but no dataframe was returned")
    
    return messages, had_error, last_df

def prepare_plot_error_message(plot_spec: Dict[str, Any], error: str, last_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """
    Prepare an error message for a failed plot.
    
    Args:
        plot_spec: The plot specification that failed
        error: The error message
        last_df: The dataframe that was being plotted (if available)
        
    Returns:
        A message dictionary to be added to the conversation
    """
    plot_type = plot_spec.get('type', 'unknown')
    
    # Create a more user-friendly error message with actionable guidance
    error_content = f"{DATABASE_ACTOR}:\n\n**Error creating {plot_type} plot:**\n```\n{error}\n```"
    
    # Add available columns information if we have a dataframe
    if last_df is not None and not last_df.empty:
        available_columns = last_df.columns.tolist()
        error_content += f"\n\nAvailable columns in your data: {', '.join(available_columns)}"
    
    # Add plot specification for reference
    error_content += f"\n\nPlot specification:\n```json\n{json.dumps(plot_spec, indent=2)}\n```"
    
    # Add general guidance
    error_content += "\n\nPlease check your plot specification and try again with valid parameters."
    
    print(f"ERROR - Failed to create {plot_type} plot: {error}")
    return {"role": USER_ROLE, "content": error_content, "dataframe": last_df}

def prepare_map_error_message(map_spec: Dict[str, Any], error: str, last_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """
    Prepare an error message for a failed map.
    
    Args:
        map_spec: The map specification that failed
        error: The error message
        last_df: The dataframe that was being mapped (if available)
        
    Returns:
        A message dictionary to be added to the conversation
    """
    map_type = map_spec.get('type', 'unknown')
    
    # Create a more user-friendly error message with actionable guidance
    error_content = f"{DATABASE_ACTOR}:\n\n**Error creating {map_type} map:**\n```\n{error}\n```"
    
    # Add available columns information if we have a dataframe
    if last_df is not None and not last_df.empty:
        available_columns = last_df.columns.tolist()
        error_content += f"\n\nAvailable columns in your data: {', '.join(available_columns)}"
    
    # Add map specification for reference
    error_content += f"\n\nMap specification:\n```json\n{json.dumps(map_spec, indent=2)}\n```"
    
    # Add general guidance
    error_content += "\n\nPlease check your map specification and try again with valid parameters."
    
    print(f"ERROR - Failed to create {map_type} map: {error}")
    return {"role": USER_ROLE, "content": error_content, "dataframe": last_df}

def prepare_no_data_error_message() -> Dict[str, Any]:
    """
    Prepare an error message when no data is available for visualization.
    
    Returns:
        A message dictionary to be added to the conversation
    """
    error_content = f"{DATABASE_ACTOR}:\n\n**No data available for visualization**\n\nYou need to run a SELECT query to retrieve data before creating a visualization. For example:\n```sql\nSELECT * FROM your_table;\n```\n\nThe most recent SQL statement did not return any data, which is common with INSERT, UPDATE, DELETE, or CREATE statements."
    
    print(f"ERROR - No data available for visualization")
    return {"role": USER_ROLE, "content": error_content} 