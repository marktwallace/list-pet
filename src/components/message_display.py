"""
Message display components for the List Pet application.
Handles rendering of different message types in the Streamlit UI.
"""

import streamlit as st
import re
import pandas as pd
import traceback
import json

from ..message_manager import get_message_manager
from ..sql_utils import extract_table_name_from_sql
from ..constants import ASSISTANT_ROLE, USER_ROLE, USER_ACTOR, DATABASE_ACTOR

def display_message(message: dict):
    """Display a message in user-friendly format."""
    message_manager = get_message_manager()
    messages = message_manager.get_messages()
    
    # Add debug logging for message content
    print(f"DEBUG - Displaying message: role={message.get('role')}, keys={list(message.keys())}")
    
    with st.chat_message(message["role"]):
        # Handle assistant messages (AI responses)
        if message["role"] == ASSISTANT_ROLE:
            parsed = parse_markup(message["content"])
            display_text = "\n\n".join(item["text"] for item in parsed.get("display", []))
            st.markdown(display_text)
            return
        
        # Handle database actor messages (SQL results, plots, maps)
        content = message.get("content", "")
        if content.startswith(f"{DATABASE_ACTOR}:"):
            _display_database_message(message, messages)
            return
        
        # Handle regular user messages
        st.markdown(content)

def _display_database_message(message: dict, messages: list):
    """Display a database message with SQL results, plots, or maps."""
    content = message.get("content", "")
    
    # Extract the main message content without SQL blocks or results
    clean_content = re.sub(r"```(?:sql)?\s*\n?.*?\n?```", "", content, flags=re.DOTALL)
    clean_content = re.sub(r"Result:.*?(?=\n\n|\Z)", "", clean_content, flags=re.DOTALL)
    clean_content = re.sub(r"No data to display", "", clean_content, flags=re.DOTALL)
    clean_content = clean_content.strip()
    
    # Display the cleaned content text (main message)
    if clean_content:
        st.markdown(clean_content)
    
    # Handle SQL query display
    _display_sql_query(message, content)
    
    # Handle error messages
    if "Error:" in content:
        error_match = re.search(r"Error:.*?```(.*?)```", content, re.DOTALL)
        if error_match:
            st.error(f"```\n{error_match.group(1).strip()}\n```")
    
    # Handle actual figures (plots)
    if "figure" in message:
        _display_plot(message, messages)
    
    # Handle actual maps
    elif "map_figure" in message:
        _display_map(message, messages)
    
    # Handle actual dataframes
    elif "dataframe" in message and isinstance(message["dataframe"], pd.DataFrame):
        _display_dataframe(message)
    
    # Handle recovered artifacts that need regeneration
    elif message.get("had_data_artifact") and "data_artifacts" in message:
        print(f"DEBUG - Found message with recoverable artifacts: message_id={message.get('message_id')}")
        print(f"DEBUG - Artifacts: {message.get('data_artifacts')}")
        display_recoverable_artifacts(message, get_message_manager())
    else:
        print(f"DEBUG - Message has no recoverable artifacts: had_data_artifact={message.get('had_data_artifact')}, has_data_artifacts={'data_artifacts' in message}")
        if message.get("had_data_artifact"):
            print(f"DEBUG - Message marked as having data artifacts but none found")
            if "message_id" in message:
                print(f"DEBUG - Message ID: {message.get('message_id')}")

def _display_sql_query(message: dict, content: str):
    """Display SQL query and its results."""
    sql_match = re.search(r"```(?:sql)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if not sql_match:
        return
        
    sql_query = sql_match.group(1).strip()
    first_line = sql_query.split('\n')[0].strip()
    with st.expander(f"SQL: {first_line}", expanded=False):
        st.markdown(f"```sql\n{sql_query}\n```")
    
    # Check if we have a dataframe in the message object
    if "dataframe" in message and isinstance(message["dataframe"], pd.DataFrame):
        # If we have a dataframe, we'll display it separately, so we don't need to show the text result
        return
    
    # Extract and display result separately if no dataframe is available
    result_match = re.search(r"Result:(.*?)(?=\n\n|\Z)", content, flags=re.DOTALL)
    if not result_match:
        return
        
    result_text = result_match.group(1).strip()
    
    # Check if this is a SELECT result with TSV/CSV data
    if "```tsv" in result_text or "```csv" in result_text:
        # Try to convert the TSV/CSV text to a dataframe
        try:
            # Extract the TSV/CSV content
            tsv_match = re.search(r"```(?:tsv|csv)\n(.*?)\n```", result_text, re.DOTALL)
            if tsv_match:
                tsv_content = tsv_match.group(1).strip()
                lines = tsv_content.split('\n')
                if len(lines) > 0:
                    # Parse the header and data
                    headers = lines[0].split('\t')
                    data = []
                    for line in lines[1:]:
                        if line.strip():
                            data.append(line.split('\t'))
                    
                    # Create a dataframe
                    df = pd.DataFrame(data, columns=headers)
                    
                    # Determine a good title for the dataframe expander
                    df_title = "Data"
                    if sql_query:
                        # Try to extract table name from query
                        table_name = extract_table_name_from_sql(sql_query)
                        if table_name:
                            df_title = f"Data from {table_name}"
                    
                    # Display as Streamlit dataframe
                    with st.expander(f"📊 {df_title}", expanded=True):
                        st.dataframe(
                            df,
                            use_container_width=True,
                            hide_index=True,
                            column_config={ col: st.column_config.Column(width="auto") for col in df.columns }
                        )
                        
                        # Show row and column count
                        st.caption(f"{len(df)} rows × {len(df.columns)} columns")
                    
                    # Skip the text-based result display by returning early
                    return
        except Exception as e:
            print(f"ERROR - Failed to convert TSV/CSV to dataframe: {str(e)}")
            # Fall back to text display
    
    # For non-TSV/CSV results or if conversion failed
    result_preview = result_text.split('\n')[0].strip() if result_text else "success, no data"
    if result_text and "No data to display" not in result_text:
        with st.expander(f"Result: {result_preview}", expanded=True):
            st.markdown(f"**Output:**\n```output\n{result_text}\n```")

def _display_plot(message: dict, messages: list):
    """Display a plot figure."""
    try:
        plot_msg_id = message.get("plot_msg_id")
        if not plot_msg_id:
            msg_idx = messages.index(message)
            plot_idx = message.get("plot_index", 0)
            plot_msg_id = f"stored_plot_{msg_idx}_{plot_idx}"
        
        # Use an expander for plots - open by default for newly generated content
        plot_title = "Plot"
        if "plot_spec" in message and "title" in message["plot_spec"]:
            plot_title = message["plot_spec"]["title"]
        
        with st.expander(f"📈 {plot_title}", expanded=True):
            st.plotly_chart(message["figure"], use_container_width=True, key=plot_msg_id)
            
            # Show row and column counts if we have dataframe
            if "dataframe" in message and message["dataframe"] is not None:
                df = message["dataframe"]
                st.caption(f"{len(df)} rows × {len(df.columns)} columns")
    except Exception as e:
        error_message = f"Error displaying plot: {str(e)}"
        st.error(error_message)
        print(f"ERROR - {error_message}")
        print(f"ERROR - Plot display traceback: {traceback.format_exc()}")

def _display_map(message: dict, messages: list):
    """Display a map figure."""
    try:
        map_msg_id = message.get("map_msg_id")
        if not map_msg_id:
            msg_idx = messages.index(message)
            map_idx = message.get("map_index", 0)
            map_msg_id = f"stored_map_{msg_idx}_{map_idx}"
        
        # Use an expander for maps - open by default for newly generated content
        map_title = "Map"
        if "map_spec" in message and "title" in message["map_spec"]:
            map_title = message["map_spec"]["title"]
        
        with st.expander(f"🗺️ {map_title}", expanded=True):
            st.plotly_chart(message["map_figure"], use_container_width=True, key=map_msg_id)
            
            # Show row and column counts if we have dataframe
            if "dataframe" in message and message["dataframe"] is not None:
                df = message["dataframe"]
                st.caption(f"{len(df)} rows × {len(df.columns)} columns")
    except Exception as e:
        error_message = f"Error displaying map: {str(e)}"
        st.error(error_message)
        print(f"ERROR - {error_message}")
        print(f"ERROR - Map display traceback: {traceback.format_exc()}")

def _display_dataframe(message: dict):
    """Display a dataframe."""
    df = message["dataframe"]
    
    # Determine a good title for the dataframe expander
    df_title = "Data"
    if "query_text" in message:
        # Try to extract table name from query
        table_name = extract_table_name_from_sql(message["query_text"])
        if table_name:
            df_title = f"Data from {table_name}"
    
    # Use an expander for dataframes - open by default for newly generated content
    with st.expander(f"📊 {df_title}", expanded=True):
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={ col: st.column_config.Column(width="auto") for col in df.columns }
        )
        
        # Show row and column count
        st.caption(f"{len(df)} rows × {len(df.columns)} columns")

def display_recoverable_artifacts(message, message_manager):
    """Display recoverable artifacts with regeneration options."""
    print(f"DEBUG - Displaying recoverable artifacts for message: {message.get('message_id')}")
    print(f"DEBUG - Data artifacts: {len(message.get('data_artifacts', []))}")
    
    for artifact in message["data_artifacts"]:
        artifact_type = artifact.get("type", "unknown")
        query_text = artifact.get("query_text")
        
        print(f"DEBUG - Processing artifact: type={artifact_type}, has_query={query_text is not None}")
        print(f"DEBUG - Artifact details: {artifact}")
        
        # Create a visual separator between artifacts if there are multiple
        if artifact != message["data_artifacts"][0]:
            st.divider()
        
        # Determine the expander title based on artifact type
        if artifact_type == "dataframe":
            # Try to extract table name from query for a better title
            expander_title = "📊 Dataframe"
            if query_text:
                table_name = extract_table_name_from_sql(query_text)
                if table_name:
                    expander_title = f"📊 Data from {table_name}"
        elif artifact_type == "plot":
            expander_title = "📈 Plot"
            # Check if we have plot title in metadata
            if "metadata" in artifact and "plot_spec" in artifact["metadata"]:
                plot_spec = artifact["metadata"]["plot_spec"]
                if "title" in plot_spec:
                    expander_title = f"📈 {plot_spec['title']}"
        elif artifact_type == "map":
            expander_title = "🗺️ Map"
            # Check if we have map title in metadata
            if "metadata" in artifact and "map_spec" in artifact["metadata"]:
                map_spec = artifact["metadata"]["map_spec"]
                if "title" in map_spec:
                    expander_title = f"🗺️ {map_spec['title']}"
        else:
            expander_title = f"📄 {artifact_type.capitalize()}"
        
        # Add recovery indicator to the title
        expander_title += " (Recoverable)"
        
        # Create an expander for this artifact - closed by default for recovered content
        with st.expander(expander_title, expanded=False):
            _display_artifact_content(artifact, message_manager)

def _display_artifact_content(artifact, message_manager):
    """Display the content of a recoverable artifact."""
    query_text = artifact.get("query_text")
    
    # Add regeneration button at the top of the expander
    if query_text:
        button_key = f"regen_{artifact.get('id')}"
        print(f"DEBUG - Button key: {button_key}")
        regenerate = st.button(
            f"Regenerate {artifact.get('type', 'Data').capitalize()}", 
            key=button_key,
            type="primary",
            use_container_width=True  # Make button full width
        )
        print(f"DEBUG - Button created with key: {button_key}")
    
    # Show SQL query
    if query_text:
        st.write("**SQL Query:**")
        st.code(query_text, language="sql")
    else:
        st.warning("Cannot regenerate this data (no SQL query available)")
        print(f"DEBUG - No query_text available for artifact {artifact.get('id')}, cannot add regenerate button")
    
    # Show metadata
    if "metadata" in artifact:
        metadata = artifact.get("metadata", {})
        print(f"DEBUG - Metadata: {metadata}")
        
        # Display basic metadata
        if "columns" in metadata:
            st.caption(f"Columns: {', '.join(metadata['columns'])}")
        if "shape" in metadata:
            st.caption(f"Data shape: {metadata['shape'][0]} rows × {metadata['shape'][1]} columns")
        
        # For dataframes, show a preview of the structure and sample data if available
        if artifact.get("type") == "dataframe" and "columns" in metadata:
            _display_dataframe_preview(metadata)
        
        # For plots, show plot type and key parameters
        if artifact.get("type") == "plot" and "plot_spec" in metadata:
            _display_plot_metadata(metadata["plot_spec"])
        
        # For maps, show map type and key parameters
        if artifact.get("type") == "map" and "map_spec" in metadata:
            _display_map_metadata(metadata["map_spec"])
    
    # Handle regeneration
    if query_text and 'regenerate' in locals() and regenerate:
        _handle_artifact_regeneration(artifact, message_manager)

def _display_dataframe_preview(metadata):
    """Display a preview of a dataframe from its metadata."""
    # Show sample data if available
    if "sample_data" in metadata and metadata["sample_data"]:
        print(f"DEBUG - Sample data available: {len(metadata['sample_data'])} rows")
        st.write("**Data Preview:**")
        try:
            # Convert sample data to dataframe
            sample_df = pd.DataFrame(metadata["sample_data"])
            st.dataframe(
                sample_df,
                use_container_width=True,
                hide_index=True
            )
            st.caption("(Preview of first few rows - regenerate to see full data)")
        except Exception as e:
            error_msg = f"Could not display data preview: {str(e)}"
            st.warning(error_msg)
            print(f"ERROR - {error_msg}")
    else:
        print("DEBUG - No sample data available, showing structure preview")
        # Show structure preview if no sample data
        st.write("**Data Structure Preview:**")
        # Create a sample dataframe structure
        cols = metadata["columns"]
        sample_data = {col: ["..."] for col in cols}
        sample_df = pd.DataFrame(sample_data)
        st.dataframe(
            sample_df,
            use_container_width=True,
            hide_index=True
        )

def _display_plot_metadata(plot_spec):
    """Display metadata for a plot specification."""
    plot_type = plot_spec.get("type", "unknown")
    st.caption(f"Plot type: {plot_type}")
    
    # Show key plot parameters
    params = []
    for key in ["x", "y", "color", "size", "title"]:
        if key in plot_spec:
            params.append(f"{key}={plot_spec[key]}")
    if params:
        st.caption(f"Parameters: {', '.join(params)}")

def _display_map_metadata(map_spec):
    """Display metadata for a map specification."""
    map_type = map_spec.get("type", "unknown")
    st.caption(f"Map type: {map_type}")
    
    # Show key map parameters
    params = []
    for key in ["lat", "lon", "color", "size", "title", "locations", "geojson"]:
        if key in map_spec:
            params.append(f"{key}={map_spec[key]}")
    if params:
        st.caption(f"Parameters: {', '.join(params)}")

def _handle_artifact_regeneration(artifact, message_manager):
    """Handle regeneration of an artifact from its stored query."""
    artifact_type = artifact.get("type", "unknown")
    query_text = artifact.get("query_text")
    
    print(f"DEBUG - Regenerate button clicked for {artifact_type}")
    with st.spinner(f"Regenerating {artifact_type}..."):
        try:
            from ..database import get_database
            db = get_database()
            
            # Execute the query to get the dataframe
            from ..sql_utils import execute_sql
            result, is_error, df = execute_sql(query_text, db)
            
            if is_error or df is None:
                error_msg = f"Failed to regenerate data: {result}"
                st.error(error_msg)
                print(f"ERROR - {error_msg}")
            else:
                print(f"DEBUG - Query executed successfully, dataframe shape: {df.shape}")
                # For dataframe only, just display it
                if artifact_type == "dataframe":
                    message_manager.add_database_message(
                        f"Regenerated data from query:\n```sql\n{query_text}\n```", 
                        dataframe=df,
                        query_text=query_text
                    )
                    st.success(f"Dataframe regenerated successfully with {len(df)} rows")
                # For plots, recreate the plot
                elif artifact_type == "plot" and "metadata" in artifact:
                    _regenerate_plot(artifact, df, message_manager, query_text)
                # For maps, recreate the map
                elif artifact_type == "map" and "metadata" in artifact:
                    _regenerate_map(artifact, df, message_manager, query_text)
                
                # Force a rerun to show the new message
                print("DEBUG - Forcing rerun to show new message")
                st.rerun()
        except Exception as e:
            error_msg = f"Error regenerating data: {str(e)}"
            st.error(error_msg)
            print(f"ERROR - Regeneration error: {str(e)}")
            print(f"ERROR - Regeneration traceback: {traceback.format_exc()}")

def _regenerate_plot(artifact, df, message_manager, query_text):
    """Regenerate a plot from its specification and dataframe."""
    metadata = artifact.get("metadata", {})
    if "plot_spec" in metadata:
        plot_spec = metadata["plot_spec"]
        from ..plotting import get_plotter
        plotter = get_plotter()
        fig, error = plotter.create_plot(plot_spec, df)
        if error:
            st.error(f"Failed to regenerate plot: {error}")
        else:
            message_manager.add_plot_message(
                df, fig, 0, plot_spec, query_text
            )
            st.success("Plot regenerated successfully")

def _regenerate_map(artifact, df, message_manager, query_text):
    """Regenerate a map from its specification and dataframe."""
    metadata = artifact.get("metadata", {})
    if "map_spec" in metadata:
        map_spec = metadata["map_spec"]
        from ..mapping import get_mapper
        mapper = get_mapper()
        fig, error = mapper.create_map(map_spec, df)
        if error:
            st.error(f"Failed to regenerate map: {error}")
        else:
            message_manager.add_map_message(
                df, fig, 0, map_spec, query_text
            )
            st.success("Map regenerated successfully")

# Import parse_markup from parse.py to avoid circular imports
from ..parse import parse_markup 