import streamlit as st
from .commands import get_logger
from .constants import ASSISTANT_ROLE, USER_ROLE, USER_ACTOR, DATABASE_ACTOR
from .database import get_database
import os
import uuid
import re
import pandas as pd
import traceback
from .parse import parse_markup
from .sql_utils import extract_table_name_from_sql

class MessageManager:
    """
    Class to manage conversation messages with integrated logging.
    Encapsulates operations on st.session_state.messages.
    """
    
    def __init__(self):
        """Initialize the message manager and ensure session state is set up."""
        self.logger = get_logger()
        self.db = get_database()
        self._initialize_session_state()
    
    def _initialize_session_state(self):
        """Initialize session state messages if they don't exist."""
        if "messages" not in st.session_state:
            # Try to load messages from the database first
            db_messages = self.db.load_messages()
            if db_messages:
                print(f"DEBUG - Loaded {len(db_messages)} messages from database")
                st.session_state.messages = db_messages
            else:
                st.session_state.messages = []
                
                # Add the first assistant message if available
                try:
                    with open('prompts/first.txt', 'r') as f:
                        first_message = f.read()
                    self.add_assistant_message(first_message)
                except Exception as e:
                    print(f"ERROR - Failed to load first message: {str(e)}")
    
    def get_messages(self):
        """Get all messages in the conversation."""
        return st.session_state.messages
    
    def format_sql_result(self, query: str, df: pd.DataFrame | None, error: str | None) -> tuple[str, pd.DataFrame | None]:
        """Format SQL results in a consistent way, returning both display text and dataframe.
        
        This follows the UI guidelines for displaying SQL results.
        """
        output = []
        output.append(f"```sql\n{query}\n```")
        
        if error:
            # For actual errors, show as errors
            if error.startswith("SQL Error:"):
                output.append("Error:")
                output.append(f"```\n{error}\n```")
            # For informational messages, show as results
            else:
                output.append("Result:")
                output.append(f"```\n{error}\n```")
            return "\n".join(output), None
        elif df is not None:
            tsv_output = []
            tsv_output.append("\t".join(df.columns))
            for _, row in df.iterrows():
                tsv_output.append("\t".join(str(val) for val in row))
            
            output.append("Result:")
            output.append("```tsv\n" + "\n".join(tsv_output) + "\n```")
            return "\n".join(output), df
        else:
            # Handle case where there's no error and no dataframe
            # This happens for successful operations that don't return data
            output.append("Result:")
            
            # Determine the appropriate message based on the query type
            if query.strip().upper().startswith("CREATE"):
                output.append("```\nCREATE operation completed. No data to display.\n```")
            elif query.strip().upper().startswith("INSERT"):
                output.append("```\nINSERT operation completed. No data to display.\n```")
            elif query.strip().upper().startswith("UPDATE"):
                output.append("```\nUPDATE operation completed. No data to display.\n```")
            elif query.strip().upper().startswith("DELETE"):
                output.append("```\nDELETE operation completed. No data to display.\n```")
            elif query.strip().upper().startswith("DROP"):
                output.append("```\nDROP operation completed. No data to display.\n```")
            elif query.strip().upper().startswith("ALTER"):
                output.append("```\nALTER operation completed. No data to display.\n```")
            else:
                output.append("```\nOperation completed. No data to display.\n```")
        
        return "\n".join(output), None
    
    def execute_sql(self, query: str, db=None) -> tuple[str, bool, pd.DataFrame | None]:
        """Execute SQL and return (formatted_result, had_error, dataframe).
        
        This method encapsulates the SQL execution and formatting in one place,
        following the UI guidelines.
        """
        if db is None:
            db = self.db
            
        df, error = db.execute_query(query)
        result, df = self.format_sql_result(query, df, error)
        # Only consider it an error if the error message starts with "SQL Error:"
        return result, bool(error and error.startswith("SQL Error:")), df
    
    def add_message(self, message):
        """Add a message to the conversation and log it."""
        st.session_state.messages.append(message)
        self.logger.log_message(message)
        # Also log to database
        self.db.log_message(message)
    
    def add_user_message(self, content):
        """Add a user message to the conversation."""
        formatted_content = f"{USER_ACTOR}: {content}"
        message = {"role": USER_ROLE, "content": formatted_content}
        self.add_message(message)
        return message
    
    def add_assistant_message(self, content):
        """Add an assistant message to the conversation."""
        message = {"role": ASSISTANT_ROLE, "content": content}
        self.add_message(message)
        return message
    
    def add_database_message(self, content, dataframe=None, query_text=None):
        """Add a database message to the conversation."""
        formatted_content = f"{DATABASE_ACTOR}:\n{content}"
        message = {"role": USER_ROLE, "content": formatted_content}
        
        # If a dataframe is provided, store it
        if dataframe is not None:
            # Generate a unique ID for the dataframe
            df_id = str(uuid.uuid4())
            
            # Create metadata about the dataframe
            metadata = {
                "columns": dataframe.columns.tolist(),
                "shape": dataframe.shape,
            }
            
            # Add sample data (first few rows) to metadata for preview
            try:
                # Get first 5 rows as dict records
                sample_rows = dataframe.head(5).to_dict(orient='records')
                metadata["sample_data"] = sample_rows
            except Exception as e:
                print(f"Error creating sample data: {e}")
            
            # Store the dataframe directly in the message
            message["dataframe"] = dataframe
            message["dataframe_metadata"] = metadata
            
            # Store in data_artifacts table
            if query_text:
                self.db.store_data_artifact(
                    message_id=len(st.session_state.messages),  # Current message index
                    artifact_type="dataframe",
                    metadata=metadata,
                    query_text=query_text
                )
        
        # Add query_text if provided
        if query_text is not None:
            message["query_text"] = query_text
        
        self.add_message(message)
        return message
    
    def add_plot_message(self, dataframe, figure, plot_index=0, plot_spec=None, query_text=None):
        """Add a plot message to the conversation."""
        # Get the current message count for a unique ID
        message_count = len(st.session_state.messages)
        plot_msg_id = f"plot_{message_count}_{plot_index}"
        
        # Create metadata about the dataframe
        metadata = {}
        if dataframe is not None:
            metadata = {
                "columns": dataframe.columns.tolist(),
                "shape": dataframe.shape,
            }
            
            # Add sample data (first few rows) to metadata for preview
            try:
                # Get first 5 rows as dict records
                sample_rows = dataframe.head(5).to_dict(orient='records')
                metadata["sample_data"] = sample_rows
            except Exception as e:
                print(f"Error creating sample data: {e}")
        
        # Add plot specification to metadata
        if plot_spec:
            metadata["plot_spec"] = plot_spec
        
        # Create a descriptive title for the plot
        plot_title = "Plot created successfully"
        if plot_spec and "title" in plot_spec:
            plot_title = f"Plot: {plot_spec['title']}"
        
        message = {
            "role": USER_ROLE, 
            "content": f"{DATABASE_ACTOR}:\n{plot_title}", 
            "dataframe": dataframe,
            "figure": figure,
            "plot_index": plot_index,
            "plot_msg_id": plot_msg_id,
            "plot_metadata": metadata
        }
        
        # Store plot specification and query text for potential regeneration
        if plot_spec:
            message["plot_spec"] = plot_spec
        if query_text:
            message["query_text"] = query_text
        
        # Store in data_artifacts table
        if query_text:
            self.db.store_data_artifact(
                message_id=len(st.session_state.messages),  # Current message index
                artifact_type="plot",
                metadata=metadata,
                query_text=query_text
            )
        
        self.add_message(message)
        return message
    
    def add_map_message(self, dataframe, map_figure, map_index=0, map_spec=None, query_text=None):
        """Add a map message to the conversation."""
        # Get the current message count for a unique ID
        message_count = len(st.session_state.messages)
        map_msg_id = f"map_{message_count}_{map_index}"
        
        # Create metadata about the dataframe
        metadata = {}
        if dataframe is not None:
            metadata = {
                "columns": dataframe.columns.tolist(),
                "shape": dataframe.shape,
            }
            
            # Add sample data (first few rows) to metadata for preview
            try:
                # Get first 5 rows as dict records
                sample_rows = dataframe.head(5).to_dict(orient='records')
                metadata["sample_data"] = sample_rows
            except Exception as e:
                print(f"Error creating sample data: {e}")
        
        # Add map specification to metadata
        if map_spec:
            metadata["map_spec"] = map_spec
        
        # Create a descriptive title for the map
        map_title = "Map created successfully"
        if map_spec and "title" in map_spec:
            map_title = f"Map: {map_spec['title']}"
        
        message = {
            "role": USER_ROLE, 
            "content": f"{DATABASE_ACTOR}:\n{map_title}", 
            "dataframe": dataframe,
            "map_figure": map_figure,
            "map_index": map_index,
            "map_msg_id": map_msg_id,
            "map_metadata": metadata
        }
        
        # Store map specification and query text for potential regeneration
        if map_spec:
            message["map_spec"] = map_spec
        if query_text:
            message["query_text"] = query_text
        
        # Store in data_artifacts table
        if query_text:
            self.db.store_data_artifact(
                message_id=len(st.session_state.messages),  # Current message index
                artifact_type="map",
                metadata=metadata,
                query_text=query_text
            )
        
        self.add_message(message)
        return message
        
    def display_recoverable_artifacts(self, message):
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
                            # Execute the query to get the dataframe
                            result, is_error, df = self.execute_sql(query_text)
                            
                            if is_error or df is None:
                                error_msg = f"Failed to regenerate data: {result}"
                                st.error(error_msg)
                                print(f"ERROR - {error_msg}")
                            else:
                                print(f"DEBUG - Query executed successfully, dataframe shape: {df.shape}")
                                # For dataframe only, just display it
                                if artifact_type == "dataframe":
                                    self.add_database_message(
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
                                        from .plotting import get_plotter
                                        plotter = get_plotter()
                                        fig, error = plotter.create_plot(plot_spec, df)
                                        if error:
                                            st.error(f"Failed to regenerate plot: {error}")
                                        else:
                                            self.add_plot_message(
                                                df, fig, 0, plot_spec, query_text
                                            )
                                            st.success("Plot regenerated successfully")
                                # For maps, recreate the map
                                elif artifact_type == "map" and "metadata" in artifact:
                                    metadata = artifact.get("metadata", {})
                                    if "map_spec" in metadata:
                                        map_spec = metadata["map_spec"]
                                        from .mapping import get_mapper
                                        mapper = get_mapper()
                                        fig, error = mapper.create_map(map_spec, df)
                                        if error:
                                            st.error(f"Failed to regenerate map: {error}")
                                        else:
                                            self.add_map_message(
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
        
    def display_message(self, message):
        """Display a message in user-friendly format following UI guidelines."""
        messages = self.get_messages()
        
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
                    self.display_recoverable_artifacts(message)
                else:
                    print(f"DEBUG - Message has no recoverable artifacts: had_data_artifact={message.get('had_data_artifact')}, has_data_artifacts={'data_artifacts' in message}")
                    if message.get("had_data_artifact"):
                        print(f"DEBUG - Message marked as having data artifacts but none found")
                        if "message_id" in message:
                            print(f"DEBUG - Message ID: {message.get('message_id')}")
                
                return
            
            # Handle regular user messages
            st.markdown(content)

def get_message_manager():
    """Get or create the message manager instance."""
    if "message_manager" not in st.session_state:
        st.session_state.message_manager = MessageManager()
    return st.session_state.message_manager 