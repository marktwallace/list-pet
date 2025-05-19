from datetime import datetime
import os
import re
import traceback
import sys

import duckdb
import streamlit as st
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Set pandas display options for better float formatting
pd.set_option('display.float_format', lambda x: '{:.3f}'.format(x) if abs(x) < 1000 else '{:.1f}'.format(x))

from langchain_core.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    AIMessagePromptTemplate,
    ChatPromptTemplate
)
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from .prompt_loader import get_prompts
from .database import Database
from .parsing import get_elements, SQL_REGEX
from .chart_renderer import render_chart
from .llm_handler import LLMHandler
from .conversation_manager import ConversationManager, USER_ROLE, ASSISTANT_ROLE, SYSTEM_ROLE
from .ui_styles import CODE_WRAP_STYLE, CONVERSATION_BUTTON_STYLE, TRAIN_ICON
from .python_executor import execute_python_code

conv_manager = None

avatars = {
    USER_ROLE: "assets/avatars/data_scientist_128px.png",
    ASSISTANT_ROLE: "assets/avatars/list_pet_128px.png",
    SYSTEM_ROLE: "assets/avatars/list_pet_128px.png"
}

def title_text(input):
    """Helper function to truncate titles"""
    return input if len(input) <= 120 else input[:117] + "..."

def validate_element_indices(attributes, required_attrs, element_type="element"):
    """
    Validates and converts message and tag indices from attributes.
    Returns (msg_idx, tag_idx) tuple or (None, None) if validation fails.
    """
    for attr_msg, attr_tag, desc in required_attrs:
        if attr_msg not in attributes or attr_tag not in attributes:
            st.error(f"Missing {desc} message or tag index for {element_type}")
            return None, None
            
        try:
            msg_idx = int(attributes[attr_msg])
            tag_idx = int(attributes[attr_tag])
            return msg_idx, tag_idx
        except (ValueError, IndexError) as e:
            st.error(f"Error processing {desc} indices: {str(e)}")
            return None, None

def update_dataframe_mapping(sess, sql: str, dataframe_key: str) -> str:
    """
    Extract table name from SQL and update the latest_dataframes mapping.
    Returns the new dataframe name.
    """
    # Extract table name from SQL
    table_match = re.search(r"FROM\s+(\w+(?:\.\w+)?)", sql, re.IGNORECASE)
    table_name = table_match.group(1) if table_match else "unknown"
    
    # Update table counter and latest_dataframes mapping
    if table_name not in sess.table_counters:
        sess.table_counters[table_name] = 1
    else:
        sess.table_counters[table_name] += 1
    
    dataframe_name = f"{table_name}_{sess.table_counters[table_name]}"
    sess.latest_dataframes[table_name] = dataframe_name
    return dataframe_name

def handle_regenerate_button(button_key, sql, db, dataframe_key):
    """Handle regeneration button for dataframes and figures"""
    if st.button("🔍 Regenerate", key=button_key, type="secondary", use_container_width=False):
        df, err = db.execute_query(sql)
        if err:
            print(f"ERROR - {err} for regeneration while rerunning SQL: {sql}")
            return False
        else:
            update_dataframe_mapping(st.session_state, sql, dataframe_key)
            st.session_state[dataframe_key] = df
            st.rerun()
    return False

def display_dataframe_item(item, idx, sess, db):
    """Display a dataframe element with its expander and regeneration button if needed"""
    content = item["content"]
    attributes = item["attributes"]
    dataframe_name = attributes["name"]
    display_name = attributes.get("display_name", attributes.get("table", dataframe_name))
    
    with st.expander(title_text(display_name), expanded=True):
        key = "dataframe_" + dataframe_name
        if key in sess:
            df = sess[key]
            # Format float display without modifying underlying data
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    col: st.column_config.NumberColumn(
                        format="%.4f"
                    ) for col in df.select_dtypes(include=['float64']).columns
                }
            )
            return
        
        # Validate indices
        sql_msg_idx, sql_tag_idx = validate_element_indices(
            attributes,
            [("sql_msg_idx", "sql_tag_idx", "SQL")],
            "dataframe"
        )
        if sql_msg_idx is None:
            return
            
        msg_ref_content = sess.db_messages[sql_msg_idx]["content"]
        msg_ref = get_elements(msg_ref_content)
        arr = msg_ref.get("sql", [])
        
        if arr and sql_tag_idx < len(arr):
            sql = arr[sql_tag_idx]["content"]
            button_key = f"df_btn_{idx}_{sql_msg_idx}_{sql_tag_idx}"
            handle_regenerate_button(button_key, sql, db, key)
        else:
            st.error("Missing sql for dataframe regeneration")

def get_figure_key(idx, dataframe_name, chart_content):
    """Generate a unique figure key based on index, dataframe name and chart content"""
    content_hash = hash(chart_content) % 100000  # Keep it to 5 digits
    return f"figure_{idx}_{dataframe_name}_{content_hash}"

def display_figure_item(item, idx, sess, db):
    """Display a figure element with its expander and regeneration button if needed"""
    content = item["content"]
    attributes = item["attributes"]
    dataframe_name = attributes["dataframe"]
    dataframe_key = "dataframe_" + dataframe_name
    
    # Validate both SQL and chart indices
    sql_msg_idx, sql_tag_idx = validate_element_indices(
        attributes,
        [("sql_msg_idx", "sql_tag_idx", "SQL")],
        "figure"
    )
    if sql_msg_idx is None:
        return
        
    chart_msg_idx, chart_tag_idx = validate_element_indices(
        attributes,
        [("chart_msg_idx", "chart_tag_idx", "chart")],
        "figure"
    )
    if chart_msg_idx is None:
        return
    
    # Get SQL array from message content
    sql_msg_content = sess.db_messages[sql_msg_idx]["content"]
    sql_elements = get_elements(sql_msg_content)
    sql_arr = sql_elements.get("sql", [])
    
    # Create a unique figure key using the chart content
    chart_msg = sess.db_messages[chart_msg_idx]["content"]
    msg_elements = get_elements(chart_msg)
    chart_arr = msg_elements.get("chart", [])
    
    if not chart_arr or chart_tag_idx >= len(chart_arr):
        st.error("Could not find chart configuration in message history")
        return
        
    chart_content = chart_arr[chart_tag_idx]["content"]
    figure_key = get_figure_key(idx, dataframe_name, chart_content)
    
    # Use the figure content as the title (it should contain only the title text)
    title = content.strip()
    
    # Fallback if title is empty
    if not title:
        display_name = dataframe_name.split("_")[0] if "_" in dataframe_name else dataframe_name
        title = f"Chart for {display_name}"
    
    with st.expander(title_text(title), expanded=True):
        # If dataframe exists, render chart or retrieve from cache
        if dataframe_key in sess:
            # Check if figure is already cached in session state
            if figure_key in sess:
                cached = sess[figure_key]
                if "error" in cached:
                    st.error(f"Error rendering chart: {cached['error']}")
                    st.dataframe(sess[dataframe_key], use_container_width=True, hide_index=True)
                else:
                    st.plotly_chart(cached["figure"], use_container_width=True, key=figure_key)
            else:
                # If not cached, render it now (this should rarely happen after our changes)
                df = sess[dataframe_key]
                fig, err = render_chart(df, chart_content)
                if err:
                    sess[figure_key] = {"error": err}
                    st.error(f"Error rendering chart: {err}")
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    sess[figure_key] = {"figure": fig}
                    st.plotly_chart(fig, use_container_width=True, key=figure_key)
            return
        
        # Dataframe doesn't exist, show regeneration button
        st.info(f"The dataframe '{dataframe_name}' is not available. Click the button below to regenerate it.")
        
        if sql_arr and sql_tag_idx < len(sql_arr):
            sql = sql_arr[sql_tag_idx]["content"]
            button_key = f"fig_btn_{idx}_{sql_msg_idx}_{sql_tag_idx}"
            if handle_regenerate_button(button_key, sql, db, dataframe_key):
                # Clear the cached figure when regenerating the dataframe
                if figure_key in sess:
                    del sess[figure_key]
        else:
            st.error("Missing SQL for figure dataframe regeneration")

def display_message(idx, message, sess, db):
    """Display a chat message with its components"""
    with st.chat_message(message["role"], avatar=avatars.get(message["role"])):
        # In dev mode, show raw content and trim button in columns
        if sess.dev_mode:
            col1, col2 = st.columns([5, 1])
            with col1:
                # For system messages, use a more descriptive expander title
                expander_title = "System Prompt" if message["role"] == SYSTEM_ROLE else "Raw Message Content"
                with st.expander(expander_title, expanded=False):
                    # Use markdown with text wrapping
                    st.markdown(f"```text\n{message['content']}\n```", unsafe_allow_html=True)
            
            # Only show trim button for non-system messages after the first message
            if message["role"] != SYSTEM_ROLE and idx > 0:
                with col2:
                    if st.button("✂️ Trim", key=f"trim_{idx}", use_container_width=True):
                        # Get message ID from database
                        results = db.conn.execute("""
                            SELECT id 
                            FROM pet_meta.message_log 
                            WHERE conversation_id = ? 
                            ORDER BY id ASC
                            LIMIT 1 OFFSET ?
                        """, [sess.current_conversation_id, idx]).fetchone()
                        
                        if results:
                            message_id = results[0]
                            if db.trim_conversation_after_message(sess.current_conversation_id, message_id):
                                # Reload conversation
                                sess.db_messages = db.load_messages(sess.current_conversation_id)
                                sess.llm_handler.messages = []  # Reset LLM history
                                # Reload messages into LLM handler
                                for msg in sess.db_messages:
                                    sess.llm_handler.add_message(msg["role"], msg["content"])
                                st.rerun()
                            else:
                                st.error("Failed to trim conversation")
                        else:
                            st.error("Could not find message ID for trimming")
        
        # Regular message display - only for non-system messages
        if message["role"] != SYSTEM_ROLE:
            msg = get_elements(message["content"])
            
            if "markdown" in msg:
                st.markdown(msg["markdown"])
            
            if "sql" in msg:
                for item in msg["sql"]:
                    with st.expander(title_text(item["content"]), expanded=False):
                        st.code(item["content"])

            if "python" in msg:
                for item in msg["python"]:
                    with st.expander(title_text(item["content"]), expanded=False):
                        st.code(item["content"], language="python")

            if "dataframe" in msg:
                for item in msg["dataframe"]:
                    display_dataframe_item(item, idx, sess, db)

            if "figure" in msg:
                for item in msg["figure"]:
                    display_figure_item(item, idx, sess, db)

            if "metadata" in msg:
                for item in msg["metadata"]:
                    with st.expander("Metadata", expanded=True):
                        st.code(item["content"])

            if "error" in msg:
                for item in msg["error"]:
                    with st.expander(title_text(item["content"]), expanded=False):
                        st.code(item["content"])

def process_sql_query(sql_tuple, db):
    """Process an SQL query and store results as a dataframe"""
    sess = st.session_state
    sql_idx, sql_item = sql_tuple
    sql = sql_item["content"]
    print(f"DEBUG - Processing SQL query: {sql[:100]}...")
    msg_idx = len(sess.db_messages) - 1
    
    # Get the full message content for table description
    message_content = sess.db_messages[msg_idx]["content"]
    
    # Extract table name from SQL for CREATE TABLE statements
    create_table_match = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+(?:\.\w+)?)", sql, re.IGNORECASE)
    description = None
    if create_table_match:
        table_name = create_table_match.group(1)
        # Parse message elements
        elements = get_elements(message_content)
        # Look for a table description with matching table attribute
        if "table_description" in elements:
            for desc in elements["table_description"]:
                if desc["attributes"].get("table") == table_name:
                    description = desc["content"]
                    print(f"DEBUG - Found description for table {table_name}: {description}")
                    break
    
    # Execute query and handle errors
    print(f"DEBUG - Executing SQL query with msg_idx={msg_idx}, sql_idx={sql_idx}")
    df, err = db.execute_query(sql, description=description)
    if err:
        print(f"DEBUG - SQL execution error: {err}")
        conv_manager.add_message(role=USER_ROLE, content=f"<error>\n{err}\n</error>\n")
        return True

    # Determine if the query was expected to return rows (SELECT, WITH ... SELECT)
    is_select_like_query = sql.strip().upper().startswith(("SELECT", "WITH"))

    if df is None:
        if is_select_like_query:
            # For SELECT-like queries, if db.execute_query returns None (and no error),
            # it implies an empty result set. We should represent this as an empty DataFrame.
            print(f"DEBUG - SELECT-like query returned None. Assuming empty result set and creating an empty DataFrame.")
            df = pd.DataFrame() # Create an empty DataFrame.
        else:
            # For non-SELECT queries (e.g., INSERT, UPDATE, DELETE without RETURNING, DDLs not creating tables),
            # df being None is expected if the command doesn't return rows.
            # No explicit message is needed; absence of error implies success.
            print(f"DEBUG - Non-SELECT SQL execution completed, df is None as expected (e.g., DDL, DML without RETURNING). No explicit message will be added.")
            return True # Signal to rerun, this SQL item is done.
    
    print(f"DEBUG - SQL execution processing, df is {'None' if df is None else ('empty' if df.empty else 'DataFrame with data')}")
        
    # Update dataframe mapping and get new name
    dataframe_name = update_dataframe_mapping(sess, sql, None)
    
    # Store dataframe in session state
    dataframe_key = f"dataframe_{dataframe_name}"
    sess[dataframe_key] = df
    
    # Format preview for display with consistent float precision
    preview_rows = min(5, len(df)) if len(df) > 20 else len(df)
    
    def format_value(val):
        if isinstance(val, float):
            return f"{val:.4f}"
        return str(val)
    
    # Handle empty DataFrame or DataFrame with no columns for TSV preview
    if df.empty:
        if not list(df.columns): # No columns (e.g. from pd.DataFrame())
            tsv_lines = ["(Query returned no columns and no rows)"]
        else: # Has columns, but no rows
            tsv_lines = ["\t".join(df.columns), "(Query returned no rows)"]
    else:
        tsv_lines = ["\t".join(df.columns)]
        tsv_lines.extend("\t".join(format_value(val) for val in row) for _, row in df.iloc[:preview_rows].iterrows())
        if preview_rows < len(df):
            tsv_lines.append("...")
    
    # Create and add dataframe message
    content = f'<dataframe name="{dataframe_name}" table="{dataframe_name}" sql_msg_idx="{msg_idx}" sql_tag_idx="{sql_idx}" >\n'
    content += "\n".join(tsv_lines) + "\n</dataframe>\n"
    
    print(f"DEBUG - Adding dataframe with name: {dataframe_name}")
    conv_manager.add_message(role=USER_ROLE, content=content)
    return True

def process_chart_request(chart_tuple):
    """Process a chart request and create a figure element"""
    sess = st.session_state
    chart_idx, chart_item = chart_tuple
    chart_content = chart_item["content"]
    chart_attrs = chart_item["attributes"]
    
    # Validate chart request
    table_name = chart_attrs.get("tablename")
    if not table_name:
        conv_manager.add_message(role=USER_ROLE, content="<error>\nChart missing tablename reference\n</error>\n")
        return True
    
    # Get the latest dataframe name for this table
    dataframe_name = sess.latest_dataframes.get(table_name)
    if not dataframe_name:
        conv_manager.add_message(role=USER_ROLE, content=f"<error>\nNo data available for table '{table_name}'\n</error>\n")
        return True
    
    # Find the dataframe and its SQL indices
    def find_dataframe_sql_indices():
        for i, msg in enumerate(reversed(sess.db_messages)):
            msg_elements = get_elements(msg["content"])
            if "dataframe" in msg_elements:
                for df_item in msg_elements["dataframe"]:
                    if df_item["attributes"].get("name") == dataframe_name:
                        msg_idx_str = df_item["attributes"].get("sql_msg_idx")
                        tag_idx_str = df_item["attributes"].get("sql_tag_idx")
                        if msg_idx_str is not None and tag_idx_str is not None:
                            return int(msg_idx_str), int(tag_idx_str)
        return None, None
    
    sql_msg_idx, sql_tag_idx = find_dataframe_sql_indices()
    if sql_msg_idx is None or sql_tag_idx is None:
        conv_manager.add_message(role=USER_ROLE, content=f"<error>\nCould not find dataframe '{dataframe_name}' in message history\n</error>\n")
        return True
    
    # Find the most recent assistant message containing a chart tag
    def find_chart_message():
        for i, msg in enumerate(reversed(sess.db_messages)):
            if msg["role"] == ASSISTANT_ROLE:
                msg_elements = get_elements(msg["content"])
                if "chart" in msg_elements:
                    return len(sess.db_messages) - 1 - i
        return None
    
    chart_msg_idx = find_chart_message()
    if chart_msg_idx is None:
        conv_manager.add_message(role=USER_ROLE, content="<error>\nCould not find assistant message with chart configuration\n</error>\n")
        return True
        
    print(f"DEBUG - Chart configuration in message {chart_msg_idx} (role={sess.db_messages[chart_msg_idx]['role']})")
    print(f"DEBUG - SQL in message {sql_msg_idx} (role={sess.db_messages[sql_msg_idx]['role']})")
    
    # Attempt to render the chart to validate configuration
    dataframe_key = "dataframe_" + dataframe_name
    if dataframe_key in sess:
        df = sess[dataframe_key]
        # Pass chart content directly without prepending tablename
        fig, err = render_chart(df, chart_content)
        figure_key = get_figure_key(chart_idx, dataframe_name, chart_content)
        
        if err:
            # Cache the error
            sess[figure_key] = {"error": err}
            conv_manager.add_message(role=USER_ROLE, content=f"<error>\nError rendering chart: {err}\n</error>\n")
            return True
        else:
            # Cache the successful figure
            sess[figure_key] = {"figure": fig}
    
    # Extract title from chart content if available
    title = None
    title_match = re.search(r'title:\s*(.*?)$', chart_content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        # Fallback title
        title = f"Chart for {dataframe_name.split('_')[0]}"
    
    # Create figure content with title in content and all indices in attributes
    figure_content = (
        f'<figure dataframe="{dataframe_name}" sql_msg_idx="{sql_msg_idx}" sql_tag_idx="{sql_tag_idx}" '
        f'chart_msg_idx="{chart_msg_idx}" chart_tag_idx="{chart_idx}">\n'
        f'{title}\n'
        f'</figure>'
    )
    
    print(f"DEBUG - Creating figure for dataframe: {dataframe_name}")
    conv_manager.add_message(role=USER_ROLE, content=figure_content)
    return True

def process_python_code(python_tuple):
    """Process a Python code block and create dataframe/metadata elements"""
    sess = st.session_state
    python_idx, python_item = python_tuple
    python_content = python_item["content"]
    python_attrs = python_item["attributes"]
    msg_idx = len(sess.db_messages) - 1
    
    # Get input dataframe if specified
    input_df = None
    if "dataframe" in python_attrs:
        dataframe_name = python_attrs["dataframe"]
        dataframe_key = "dataframe_" + dataframe_name
        if dataframe_key not in sess:
            # More helpful error message explaining the timing
            error_msg = (
                f"DataFrame '{dataframe_name}' not found. If this DataFrame should come from a SQL query, "
                "make sure to put the Python code that needs it in a separate message after the SQL has run."
            )
            conv_manager.add_message(role=USER_ROLE, content=f"<error>\n{error_msg}\n</error>\n")
            return True
        input_df = sess[dataframe_key]
    
    # Execute Python code
    result = execute_python_code(input_df, python_content)
    if result.error:
        conv_manager.add_message(role=USER_ROLE, content=f"<error>\n{result.error}\n</error>\n")
        return True
    
    # Handle output DataFrame if present
    if result.dataframe is not None:
        # Generate unique name for the output DataFrame
        base_name = python_attrs.get("output_name", "python_output")
        if base_name not in sess.table_counters:
            sess.table_counters[base_name] = 1
        else:
            sess.table_counters[base_name] += 1
        
        dataframe_name = f"{base_name}_{sess.table_counters[base_name]}"
        sess.latest_dataframes[base_name] = dataframe_name
        
        # Store DataFrame in session state
        dataframe_key = f"dataframe_{dataframe_name}"
        sess[dataframe_key] = result.dataframe
        
        # Format preview
        preview_rows = min(5, len(result.dataframe)) if len(result.dataframe) > 20 else len(result.dataframe)
        
        def format_value(val):
            if isinstance(val, float):
                return f"{val:.4f}"
            return str(val)
        
        tsv_lines = ["\t".join(result.dataframe.columns)]
        tsv_lines.extend("\t".join(format_value(val) for val in row) for _, row in result.dataframe.iloc[:preview_rows].iterrows())
        if preview_rows < len(result.dataframe):
            tsv_lines.append("...")
        
        # Create dataframe message
        content = f'<dataframe name="{dataframe_name}" table="{dataframe_name}" python_msg_idx="{msg_idx}" python_tag_idx="{python_idx}" >\n'
        content += "\n".join(tsv_lines) + "\n</dataframe>\n"
        conv_manager.add_message(role=USER_ROLE, content=content)
    
    # Handle metadata if present
    if result.metadata:
        content = "<metadata>\n"
        for key, value in result.metadata.items():
            content += f"{key}: {value}\n"
        content += "</metadata>\n"
        conv_manager.add_message(role=USER_ROLE, content=content)
    
    return True

def generate_llm_response():
    """Generate a response from the LLM and process it"""
    sess = st.session_state
    sess.pending_response = False
    response = sess.llm_handler.generate_response()
    if response is None:
        return False
    conv_manager.add_message(role=ASSISTANT_ROLE, content=response)
    msg = get_elements(response)
    sess.pending_sql = list(enumerate(msg.get("sql", [])))
    print(f"DEBUG - pending_sql: {sess.pending_sql}")
    sess.pending_chart = list(enumerate(msg.get("chart", [])))
    sess.pending_python = list(enumerate(msg.get("python", [])))
    return True

def main():
    st.set_page_config(page_title="List Pet", page_icon="🐾", layout="wide")
    
    sess = st.session_state # Get session state early
    global conv_manager # To assign to the global variable from session state

    if 'app_initialized' not in sess:
        print("DEBUG - Performing one-time application initialization...")

        # 1. Determine config_base_path
        if 'config_base_path' not in sess:
            config_base_env_var = os.environ.get("LISTPET_BASE")
            if config_base_env_var:
                sess.config_base_path = os.path.abspath(os.path.expanduser(config_base_env_var))
            else:
                sess.config_base_path = os.path.abspath(".") # Default to project root
            print(f"DEBUG - Using LISTPET_BASE: {sess.config_base_path}")

        # 2. Load environment variables from .env file at the config_base_path
        dotenv_path = os.path.join(sess.config_base_path, ".env")
        if os.path.exists(dotenv_path):
            load_dotenv(dotenv_path=dotenv_path)
            print(f"DEBUG - Loaded environment variables from: {dotenv_path}")
            sess.env_loaded = True
        else:
            print(f"DEBUG - .env file not found at: {dotenv_path}")
            sess.env_loaded = False
    
        # 3. Determine and store effective app mode
        # This check uses os.environ, which should now be populated by load_dotenv
        if 'effective_app_mode' not in sess:
            if os.environ.get("POSTGRES_CONN_STR"):
                sess.effective_app_mode = "postgres_enabled"
            elif sess.config_base_path != os.path.abspath(".") and os.environ.get("DUCKDB_FILE"): # LISTPET_BASE was set
                sess.effective_app_mode = "duckdb_custom_path"
            else:
                sess.effective_app_mode = "duckdb_default_path"
            print(f"DEBUG - Effective Application Mode set to: {sess.effective_app_mode}")

        # 4. Database connection (if DuckDB), Database instance, and ConversationManager instance
        db_file_path = None # Initialize for clarity
        if sess.effective_app_mode == "duckdb_custom_path":
            custom_db_file = os.environ.get("DUCKDB_FILE", "list_pet.db") # Default if not set
            if os.path.isabs(custom_db_file):
                db_file_path = custom_db_file
            else:
                db_file_path = os.path.join(sess.config_base_path, custom_db_file)
            print(f"DEBUG - Using DUCKDB_FILE (custom path): {db_file_path}")
            db_dir = os.path.dirname(db_file_path)
            if db_dir: # Ensure directory exists if custom_db_file includes a path
                 os.makedirs(db_dir, exist_ok=True)

        elif sess.effective_app_mode == "duckdb_default_path":
            db_directory = os.path.join(sess.config_base_path, "db")
            os.makedirs(db_directory, exist_ok=True)
            db_file_path = os.path.join(db_directory, "list_pet.db")
            print(f"DEBUG - DuckDB database path set to (default): {db_file_path}")
        
        if sess.effective_app_mode != "postgres_enabled" and db_file_path:
            if 'conn' not in sess: # Connect DuckDB only once if not using Postgres
                 sess.conn = duckdb.connect(db_file_path)
                 print(f"DEBUG - Connected to DuckDB: {db_file_path}")
        
        # Instantiate DB and ConvManager, store in session state
        if 'db' not in sess:
            sess.db = Database() # Database() should handle its own connection logic (e.g. for Postgres using env var)
            sess.db.initialize_pet_meta_schema() # This might use sess.conn if db is DuckDB
            print("DEBUG - Database object initialized and schema checked/created.")

        if 'conv_manager' not in sess:
            sess.conv_manager = ConversationManager(sess.db)
            sess.conv_manager.init_session_state() # Initializes sess.db_messages, etc.
            print("DEBUG - ConversationManager initialized.")

        sess.app_initialized = True
        print("DEBUG - One-time application initialization complete.")

    # Retrieve/assign core objects from session state for use in this run
    # This ensures that global conv_manager and local db_instance point to the persistent session objects
    conv_manager = sess.conv_manager 
    db_instance = sess.db

    # Add CSS styles
    st.markdown(CODE_WRAP_STYLE, unsafe_allow_html=True)
    st.markdown(CONVERSATION_BUTTON_STYLE, unsafe_allow_html=True)
    
    # Render UI
    with st.sidebar:
        sess.conv_manager.render_sidebar() # Use session state instance directly
    
    st.title("🐾 List Pet")
    st.caption("Your friendly SQL assistant")

    # Display chat messages
    for idx, message in enumerate(sess.db_messages):
        # Skip system message (first message) if not in dev mode
        if idx == 0 and not sess.dev_mode:
            continue
        display_message(idx, message, sess, db_instance) # Pass session-managed db_instance

    # Process pending items
    if sess.pending_python and sess.pending_python[0]:
        python_tuple = sess.pending_python.pop(0)
        if process_python_code(python_tuple):
            st.rerun()

    if sess.pending_sql and sess.pending_sql[0]:
        sql_tuple = sess.pending_sql.pop(0)
        if process_sql_query(sql_tuple, db_instance): # Pass session-managed db_instance
            st.rerun()

    if sess.pending_chart and sess.pending_chart[0]:
        chart_tuple = sess.pending_chart.pop(0)
        if process_chart_request(chart_tuple):
            st.rerun()

    if sess.pending_response:
        if generate_llm_response():
            st.rerun()
        
    # Process user input    
    user_chat_input = st.chat_input("Type your message...") # Renamed variable
    if user_chat_input:
        # Process SQL syntax
        processed_input = user_chat_input
        if re.match(SQL_REGEX, user_chat_input.strip(), re.IGNORECASE):
            processed_input = "<sql>\\n" + user_chat_input + "\\n</sql>\\n"
        
        sess.conv_manager.add_message(role=USER_ROLE, content=processed_input) # Use session state instance
        
        
        # Check for SQL in input
        msg = get_elements(processed_input)
        if msg.get("sql"):
            sess.pending_sql = list(enumerate(msg.get("sql", [])))
        else:
            sess.pending_response = True
            
        st.rerun()

