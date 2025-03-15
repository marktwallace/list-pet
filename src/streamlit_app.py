import streamlit as st
import os
import re
import json
import pandas as pd
from datetime import datetime
import plotly.express as px
import traceback

from .chat import ChatEngine, get_chat_engine
from .database import Database, get_database
from .parse import parse_markup
from .plotting import get_plotter
from .mapping import get_mapper
from .sql_utils import is_sql_query, execute_sql, format_sql_label, extract_table_name_from_sql
from .response_processor import process_sql_blocks, prepare_plot_error_message, prepare_map_error_message, prepare_no_data_error_message
from .message_manager import get_message_manager

# Import command-related utilities and constants
from .commands import is_command, handle_command
from .constants import ASSISTANT_ROLE, USER_ROLE, USER_ACTOR, DATABASE_ACTOR

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
            # Extract the main message content without SQL blocks or results
            clean_content = re.sub(r"```(?:sql)?\s*\n?.*?\n?```", "", content, flags=re.DOTALL)
            clean_content = re.sub(r"Result:.*?(?=\n\n|\Z)", "", clean_content, flags=re.DOTALL)
            clean_content = re.sub(r"No data to display", "", clean_content, flags=re.DOTALL)
            clean_content = clean_content.strip()
            
            # Display the cleaned content text (main message)
            if clean_content:
                st.markdown(clean_content)
            
            # Handle SQL query display
            sql_match = re.search(r"```(?:sql)?\s*\n?(.*?)\n?```", content, re.DOTALL)
            if sql_match:
                sql_query = sql_match.group(1).strip()
                first_line = sql_query.split('\n')[0].strip()
                with st.expander(f"SQL: {first_line}", expanded=False):
                    st.markdown(f"```sql\n{sql_query}\n```")
                
                # Check if we have a dataframe in the message object
                if "dataframe" in message and isinstance(message["dataframe"], pd.DataFrame):
                    # If we have a dataframe, we'll display it below, so we don't need to show the text result
                    pass
                else:
                    # Extract and display result separately if no dataframe is available
                    result_match = re.search(r"Result:(.*?)(?=\n\n|\Z)", content, flags=re.DOTALL)
                    if result_match:
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
                                            
                                            # No need to show SQL query again as it's already shown above
                                        
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
            
            # Handle error messages
            if "Error:" in content:
                error_match = re.search(r"Error:.*?```(.*?)```", content, re.DOTALL)
                if error_match:
                    st.error(f"```\n{error_match.group(1).strip()}\n```")
            
            # Handle actual figures (plots)
            if "figure" in message:
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
                        
                        # No need to show SQL query again as it's already shown above
                except Exception as e:
                    error_message = f"Error displaying plot: {str(e)}"
                    st.error(error_message)
                    print(f"ERROR - {error_message}")
                    print(f"ERROR - Plot display traceback: {traceback.format_exc()}")
            
            # Handle actual maps
            elif "map_figure" in message:
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
                        
                        # No need to show SQL query again as it's already shown above
                except Exception as e:
                    error_message = f"Error displaying map: {str(e)}"
                    st.error(error_message)
                    print(f"ERROR - {error_message}")
                    print(f"ERROR - Map display traceback: {traceback.format_exc()}")
            
            # Handle actual dataframes
            elif "dataframe" in message and isinstance(message["dataframe"], pd.DataFrame):
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
                    
                    # No need to show SQL query again as it's already shown above
            
            # Handle recovered artifacts that need regeneration
            elif message.get("had_data_artifact") and "data_artifacts" in message:
                print(f"DEBUG - Found message with recoverable artifacts: message_id={message.get('message_id')}")
                print(f"DEBUG - Artifacts: {message.get('data_artifacts')}")
                display_recoverable_artifacts(message, message_manager)
            else:
                print(f"DEBUG - Message has no recoverable artifacts: had_data_artifact={message.get('had_data_artifact')}, has_data_artifacts={'data_artifacts' in message}")
                if message.get("had_data_artifact"):
                    print(f"DEBUG - Message marked as having data artifacts but none found")
                    if "message_id" in message:
                        print(f"DEBUG - Message ID: {message.get('message_id')}")
            
            return
        
        # Handle regular user messages
        st.markdown(content)

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
            # Add regeneration button at the top of the expander
            if query_text:
                button_key = f"regen_{artifact.get('id')}"
                print(f"DEBUG - Button key: {button_key}")
                regenerate = st.button(
                    f"Regenerate {artifact_type.capitalize()}", 
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
                if artifact_type == "dataframe" and "columns" in metadata:
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
                
                # For plots, show plot type and key parameters
                if artifact_type == "plot" and "plot_spec" in metadata:
                    plot_spec = metadata["plot_spec"]
                    plot_type = plot_spec.get("type", "unknown")
                    st.caption(f"Plot type: {plot_type}")
                    
                    # Show key plot parameters
                    params = []
                    for key in ["x", "y", "color", "size", "title"]:
                        if key in plot_spec:
                            params.append(f"{key}={plot_spec[key]}")
                    if params:
                        st.caption(f"Parameters: {', '.join(params)}")
                
                # For maps, show map type and key parameters
                if artifact_type == "map" and "map_spec" in metadata:
                    map_spec = metadata["map_spec"]
                    map_type = map_spec.get("type", "unknown")
                    st.caption(f"Map type: {map_type}")
                    
                    # Show key map parameters
                    params = []
                    for key in ["lat", "lon", "color", "size", "title", "locations", "geojson"]:
                        if key in map_spec:
                            params.append(f"{key}={map_spec[key]}")
                    if params:
                        st.caption(f"Parameters: {', '.join(params)}")
            
            # Handle regeneration
            if query_text and 'regenerate' in locals() and regenerate:
                print(f"DEBUG - Regenerate button clicked for {artifact_type}")
                with st.spinner(f"Regenerating {artifact_type}..."):
                    try:
                        db = get_database()
                        
                        # Execute the query to get the dataframe
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
                                metadata = artifact.get("metadata", {})
                                if "plot_spec" in metadata:
                                    plot_spec = metadata["plot_spec"]
                                    plotter = get_plotter()
                                    fig, error = plotter.create_plot(plot_spec, df)
                                    if error:
                                        st.error(f"Failed to regenerate plot: {error}")
                                    else:
                                        message_manager.add_plot_message(
                                            df, fig, 0, plot_spec, query_text
                                        )
                                        st.success("Plot regenerated successfully")
                            # For maps, recreate the map
                            elif artifact_type == "map" and "metadata" in artifact:
                                metadata = artifact.get("metadata", {})
                                if "map_spec" in metadata:
                                    map_spec = metadata["map_spec"]
                                    mapper = get_mapper()
                                    fig, error = mapper.create_map(map_spec, df)
                                    if error:
                                        st.error(f"Failed to regenerate map: {error}")
                                    else:
                                        message_manager.add_map_message(
                                            df, fig, 0, map_spec, query_text
                                        )
                                        st.success("Map regenerated successfully")
                            
                            # Force a rerun to show the new message
                            print("DEBUG - Forcing rerun to show new message")
                            st.rerun()
                    except Exception as e:
                        error_msg = f"Error regenerating data: {str(e)}"
                        st.error(error_msg)
                        print(f"ERROR - Regeneration error: {str(e)}")
                        print(f"ERROR - Regeneration traceback: {traceback.format_exc()}")

def handle_ai_response(response: str, chat_engine: ChatEngine, db: Database, retry_count: int = 0) -> None:
    """Process AI response, executing any SQL and handling errors."""
    message_manager = get_message_manager()
    message_manager.add_assistant_message(response)
    
    parsed = parse_markup(response)
    print(f"DEBUG - Parsed response: {parsed}")
    
    # Process SQL blocks
    sql_messages, had_error, last_df = process_sql_blocks(parsed, db)
    
    # Check for table creation or modification in SQL blocks
    for sql_block in parsed.get("sql", []):
        sql_query = sql_block.get("sql", "").strip()
        if sql_query.upper().startswith("CREATE TABLE"):
            table_name = extract_table_name_from_sql(sql_query)
            if table_name:
                # Get the most recent user message as the request text
                request_text = None
                for msg in reversed(message_manager.get_messages()):
                    if msg["role"] == USER_ROLE and msg["content"].startswith(f"{USER_ACTOR}:"):
                        request_text = msg["content"]
                        break
                
                # Log the table creation
                db.log_table_creation(table_name, request_text)
                
                # Get row count if the table was created successfully
                if not had_error:
                    try:
                        row_count = db.get_table_row_count(table_name)
                        if row_count > 0:
                            db.log_table_creation(table_name, request_text, row_count)
                    except Exception as e:
                        print(f"ERROR - Failed to get row count for {table_name}: {str(e)}")
    
    for sql_message in sql_messages:
        message_manager.add_message(sql_message)
    
    # If no dataframe was produced in this response, try to get the last dataframe from previous messages
    if last_df is None and not parsed.get("sql", []):
        print("DEBUG - No SQL blocks in current response, looking for last dataframe in previous messages")
        # Look through messages in reverse order to find the most recent dataframe
        for message in reversed(message_manager.get_messages()[:-1]):  # Skip the message we just added
            if "dataframe" in message:
                last_df = message["dataframe"]
                if last_df is not None:
                    print(f"DEBUG - Found previous dataframe: {last_df.shape}, columns: {last_df.columns.tolist()}")
                else:
                    print("DEBUG - Found previous dataframe reference, but dataframe is None")
                break
    
    # Log whether we have a dataframe for visualization
    if parsed.get("plot", []) or parsed.get("map", []):
        if last_df is None:
            print("WARNING - No dataframe available for visualization")
        else:
            print(f"DEBUG - Dataframe available for visualization: {last_df.shape}")
    
    # Process plot specifications if we have data
    if last_df is not None and parsed.get("plot", []):
        print(f"DEBUG - Found {len(parsed.get('plot', []))} plot specifications to process")
        plotter = get_plotter()
        for i, plot_spec in enumerate(parsed.get("plot", [])):
            print(f"DEBUG - Processing plot {i+1}/{len(parsed.get('plot', []))}: {plot_spec}")
            try:
                fig, error = plotter.create_plot(plot_spec, last_df)
                if error:
                    print(f"ERROR - Plot creation failed: {error}")
                    plot_error = prepare_plot_error_message(plot_spec, error, last_df)
                    message_manager.add_message(plot_error)
                elif fig:
                    # Find the most recent SQL query that produced this dataframe
                    query_text = None
                    for msg in reversed(message_manager.get_messages()):
                        if "query_text" in msg and "dataframe" in msg and msg["dataframe"] is not None:
                            query_text = msg["query_text"]
                            break
                    
                    message_manager.add_plot_message(last_df, fig, i, plot_spec, query_text)
                    print(f"DEBUG - Plot added to messages with query: {query_text is not None}")
                else:
                    print("WARNING - No figure and no error returned from create_plot")
                    # Handle this unexpected case
                    error_message = "The plot could not be created due to an unknown error. Please check your plot specification and try again."
                    plot_error = prepare_plot_error_message(plot_spec, error_message, last_df)
                    message_manager.add_message(plot_error)
            except Exception as e:
                error_msg = f"Error creating plot: {str(e)}"
                print(f"ERROR - {error_msg}")
                traceback_str = traceback.format_exc()
                print(f"ERROR - Plot error traceback: {traceback_str}")
                plot_error = prepare_plot_error_message(plot_spec, error_msg, last_df)
                message_manager.add_message(plot_error)
    elif parsed.get("plot", []):
        print("WARNING - Plot specifications found but no dataframe available")
        plot_error = prepare_no_data_error_message()
        message_manager.add_message(plot_error)
    elif last_df is not None:
        print("DEBUG - Dataframe available but no plot specifications found")
    
    # Process map specifications if we have data
    if last_df is not None and parsed.get("map", []):
        print(f"DEBUG - Found {len(parsed.get('map', []))} map specifications to process")
        mapper = get_mapper()
        for i, map_spec in enumerate(parsed.get("map", [])):
            print(f"DEBUG - Processing map {i+1}/{len(parsed.get('map', []))}: {map_spec}")
            try:
                fig, error = mapper.create_map(map_spec, last_df)
                if error:
                    print(f"ERROR - Map creation failed: {error}")
                    map_error = prepare_map_error_message(map_spec, error, last_df)
                    message_manager.add_message(map_error)
                elif fig:
                    # Find the most recent SQL query that produced this dataframe
                    query_text = None
                    for msg in reversed(message_manager.get_messages()):
                        if "query_text" in msg and "dataframe" in msg and msg["dataframe"] is not None:
                            query_text = msg["query_text"]
                            break
                    
                    message_manager.add_map_message(last_df, fig, i, map_spec, query_text)
                    print(f"DEBUG - Map added to messages with query: {query_text is not None}")
                else:
                    print("WARNING - No figure and no error returned from create_map")
                    # Handle this unexpected case
                    error_message = "The map could not be created due to an unknown error. Please check your map specification and try again."
                    map_error = prepare_map_error_message(map_spec, error_message, last_df)
                    message_manager.add_message(map_error)
            except Exception as e:
                error_msg = f"Error creating map: {str(e)}"
                print(f"ERROR - {error_msg}")
                traceback_str = traceback.format_exc()
                print(f"ERROR - Map error traceback: {traceback_str}")
                map_error = prepare_map_error_message(map_spec, error_msg, last_df)
                message_manager.add_message(map_error)
    elif parsed.get("map", []):
        print("WARNING - Map specifications found but no dataframe available")
        map_error = prepare_no_data_error_message()
        message_manager.add_message(map_error)
    
    if had_error and retry_count == 0:
        print("DEBUG - Errors occurred during SQL execution, attempting to generate a new response")
        try:
            new_response = chat_engine.generate_response(message_manager.get_messages())
            handle_ai_response(new_response, chat_engine, db, retry_count + 1)
        except Exception as e:
            error_msg = f"Error generating new response: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Response generation traceback: {traceback.format_exc()}")
            message_manager.add_database_message("There was a problem generating a new response. Please try rephrasing your question.")

def handle_user_input(user_input: str, db: Database) -> bool:
    """Process user input, handling commands and SQL queries.
    
    Returns True if the app should rerun after processing.
    """
    message_manager = get_message_manager()
    
    is_cmd, cmd_type, cmd_label = is_command(user_input)
    if is_cmd:
        try:
            result = handle_command(cmd_type, cmd_label)
            with st.chat_message(USER_ROLE):
                st.markdown(f"{USER_ACTOR}: {user_input}")
            with st.expander("Command Output", expanded=True):
                st.text(result)
            return False
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Command execution traceback: {traceback.format_exc()}")
            message_manager.add_database_message(f"Command execution failed: {str(e)}. Please check your command syntax and try again.")
            return False
    
    # Regular user input (not a command)
    with st.chat_message(USER_ROLE):
        st.markdown(f"{USER_ACTOR}: {user_input}")
    
    message_manager.add_user_message(user_input)
    
    if is_sql_query(user_input):
        try:
            result, had_error, df = execute_sql(user_input, db)
            # Store the query text in the message for potential regeneration
            message_manager.add_database_message(result, df, user_input)
            
            # Check if this was a CREATE TABLE or ALTER TABLE statement
            if not had_error:
                sql_query = user_input.strip()
                if sql_query.upper().startswith("CREATE TABLE"):
                    table_name = extract_table_name_from_sql(sql_query)
                    if table_name:
                        # Log the table creation with the user's input as the request text
                        db.log_table_creation(table_name, user_input)
                        
                        # Get row count if data was inserted
                        try:
                            row_count = db.get_table_row_count(table_name)
                            if row_count > 0:
                                db.log_table_creation(table_name, user_input, row_count)
                        except Exception as e:
                            print(f"ERROR - Failed to get row count for {table_name}: {str(e)}")
                
                elif sql_query.upper().startswith("ALTER TABLE"):
                    table_name = extract_table_name_from_sql(sql_query)
                    if table_name:
                        # Update the altered_at timestamp
                        db.execute_query(f"""
                            UPDATE pet_meta.table_description
                            SET altered_at = CURRENT_TIMESTAMP
                            WHERE table_name = '{table_name}'
                        """)
                
                elif sql_query.upper().startswith("INSERT INTO"):
                    # Extract table name from INSERT statement
                    match = re.search(r"INSERT\s+INTO\s+(\w+(?:\.\w+)?)", sql_query, re.IGNORECASE)
                    if match:
                        table_name = match.group(1)
                        # Update row count
                        try:
                            row_count = db.get_table_row_count(table_name)
                            db.execute_query(f"""
                                UPDATE pet_meta.table_description
                                SET row_count = {row_count}
                                WHERE table_name = '{table_name}'
                            """)
                        except Exception as e:
                            print(f"ERROR - Failed to update row count for {table_name}: {str(e)}")
                
        except Exception as e:
            error_msg = f"Error executing SQL query: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - SQL execution traceback: {traceback.format_exc()}")
            message_manager.add_database_message(f"SQL execution failed: {str(e)}. Please check your query syntax and try again.")
    
    st.session_state.needs_ai_response = True
    return True

def generate_ai_response(chat_engine: ChatEngine, db: Database) -> None:
    """Generate and process AI response."""
    message_manager = get_message_manager()
    
    with st.spinner("Thinking..."):
        try:
            response = chat_engine.generate_response(message_manager.get_messages())
            handle_ai_response(response, chat_engine, db)
            st.session_state.needs_ai_response = False
        except Exception as e:
            error_msg = f"Error generating AI response: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - AI response generation traceback: {traceback.format_exc()}")
            message_manager.add_database_message("There was a problem generating a response. Please try again or rephrase your question.")
            st.session_state.needs_ai_response = False

def add_chat_input_focus() -> None:
    """Add JavaScript to focus the chat input field."""
    import streamlit.components.v1 as components
    components.html("""
        <script>
            function focusChatInput() {
                const doc = window.parent.document;
                const inputs = doc.querySelectorAll('textarea');
                for (const input of inputs) {
                    if (input.placeholder === 'Type your question here...') {
                        input.focus();
                        break;
                    }
                }
            }
            focusChatInput();
            setTimeout(focusChatInput, 100);
        </script>
    """, height=0, width=0)

def initialize_session_state() -> None:
    """Initialize session state variables if they don't exist."""
    # Initialize the message manager (which will set up messages)
    get_message_manager()
    
    if "needs_ai_response" not in st.session_state:
        st.session_state.needs_ai_response = False

def main():
    st.title("🐇 List Pet")
    st.caption("📋 An AI Data Assistant")
    
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)
    
    initialize_session_state()
    
    chat_engine = get_chat_engine("gpt-4o-mini")
    db = get_database()
    
    message_manager = get_message_manager()
    
    # Display all messages in the conversation history
    for message in message_manager.get_messages():
        display_message(message)
    
    # Handle user input if provided
    if user_input := st.chat_input("Type your question here...", key=f"chat_input_{len(message_manager.get_messages())}"):
        should_rerun = handle_user_input(user_input, db)
        if should_rerun:
            st.rerun()
    
    # Generate AI response if needed
    if st.session_state.needs_ai_response:
        generate_ai_response(chat_engine, db)
        st.rerun()
    
    # Add JavaScript to focus the chat input
    add_chat_input_focus()

if __name__ == "__main__":
    main()

