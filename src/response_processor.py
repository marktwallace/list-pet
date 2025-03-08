import json
from typing import Dict, List, Any, Tuple, Optional
import pandas as pd

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
    error_content = f"{DATABASE_ACTOR}:\n\n**Error creating {plot_type} plot:**\n```\n{error}\n```\n\nPlot specification:\n```json\n{json.dumps(plot_spec, indent=2)}\n```"
    return {"role": USER_ROLE, "content": error_content, "dataframe": last_df}

def prepare_no_data_error_message() -> Dict[str, Any]:
    """
    Prepare an error message for when plot specifications are found but no data is available.
    
    Returns:
        A message dictionary to be added to the conversation
    """
    error_content = f"{DATABASE_ACTOR}:\n\n**Error creating plot:**\n```\nNo data available for plotting. Please run a SQL query first.\n```"
    return {"role": USER_ROLE, "content": error_content} 