import json
import re
from typing import Dict, List, Any, Tuple, Optional
import pandas as pd
import traceback

from .parse import parse_markup

def process_sql_blocks(response: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Process SQL blocks from an AI response.
    
    Args:
        response: The raw AI response text
        
    Returns:
        Tuple containing:
        - The parsed response with SQL blocks removed
        - List of SQL blocks with their specifications
    """
    # Parse the response
    parsed = parse_markup(response)
    print(f"DEBUG - Parsed response: {parsed}")
    
    # Extract SQL blocks
    sql_blocks = []
    
    # Use regex to find SQL code blocks directly
    # The pattern needs to match both ```sql and ``` with content in between
    sql_pattern = r"```sql\s*\n(.*?)\n\s*```"
    sql_matches = re.findall(sql_pattern, response, re.DOTALL)
    
    # Create SQL blocks from regex matches
    for i, sql_query in enumerate(sql_matches):
        sql_query = sql_query.strip()
        if sql_query:
            block_id = f"sql_{i+1}"
            sql_block = {
                "id": block_id,
                "sql": sql_query,
                "plot_spec": None,
                "map_spec": None
            }
            
            # Check if this SQL block has an associated plot
            for plot_spec in parsed.get("plot", []):
                if plot_spec.get("sql_ref") == block_id:
                    sql_block["plot_spec"] = plot_spec
                    break
            
            # Check if this SQL block has an associated map
            for map_spec in parsed.get("map", []):
                if map_spec.get("sql_ref") == block_id:
                    sql_block["map_spec"] = map_spec
                    break
            
            sql_blocks.append(sql_block)
    
    # Remove SQL blocks from the response
    parsed_response = response
    for sql_query in sql_matches:
        sql_pattern = f"```sql\n{re.escape(sql_query)}\n```"
        parsed_response = re.sub(sql_pattern, "", parsed_response, flags=re.MULTILINE)
    
    return parsed_response, sql_blocks

def prepare_plot_error_message(error: str) -> str:
    """
    Prepare an error message for a failed plot.
    
    Args:
        error: The error message
        
    Returns:
        A formatted error message
    """
    return f"**Error creating plot:**\n```\n{error}\n```\n\nPlease check your plot specification and try again with valid parameters."

def prepare_map_error_message(error: str) -> str:
    """
    Prepare an error message for a failed map.
    
    Args:
        error: The error message
        
    Returns:
        A formatted error message
    """
    return f"**Error creating map:**\n```\n{error}\n```\n\nPlease check your map specification and try again with valid parameters."

def prepare_no_data_error_message() -> str:
    """
    Prepare an error message when no data is available for visualization.
    
    Returns:
        A formatted error message
    """
    return "**No data available for visualization**\n\nYou need to run a SELECT query to retrieve data before creating a visualization." 