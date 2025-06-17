from datetime import datetime
import os
import re
import traceback
import atexit
import base64
import streamlit.components.v1 as components

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
from .metadata_database import MetadataDatabase
from .analytic_factory import create_analytic_database, get_available_database_types
from .parsing import get_elements, SQL_REGEX
from .chart_renderer import render_chart
from .llm_handler import LLMHandler
from .conversation_manager import ConversationManager, USER_ROLE, ASSISTANT_ROLE, SYSTEM_ROLE
from .ui_styles import CODE_WRAP_STYLE, CONVERSATION_BUTTON_STYLE, TRAIN_ICON, CONTINUE_AI_PLAN_BUTTON_STYLE, ACTION_BUTTON_STYLES, SUBTLE_ACTION_BUTTON_STYLE
from .python_executor import execute_python_code

# Constants for continuation tags
AI_PROPOSES_CONTINUATION_TAG = "ai_proposes_continuation"
USER_APPROVES_CONTINUATION_TAG = "user_approves_continuation"
USER_REQUESTS_ERROR_FIX_TAG = "user_requests_error_fix"

conv_manager = None

avatars = {
    USER_ROLE: "assets/avatars/data_scientist_128px.png",
    ASSISTANT_ROLE: "assets/avatars/list_pet_128px.png",
    SYSTEM_ROLE: "assets/avatars/list_pet_128px.png"
}

def title_text(input):
    """Helper function to truncate titles"""
    return input if len(input) <= 120 else input[:117] + "..."

def create_action_buttons_html(message_id, idx, current_score):
    """Create custom HTML action buttons with proper styling and event handling"""
    
    # Determine button states
    thumbs_up_class = "action-button selected" if current_score == 1 else "action-button"
    thumbs_down_class = "action-button selected" if current_score == -1 else "action-button"
    
    # Create unique function names to avoid conflicts
    copy_func = f"copyMessage_{idx}"
    thumbs_up_func = f"thumbsUp_{idx}"
    thumbs_down_func = f"thumbsDown_{idx}"
    edit_func = f"editMessage_{idx}"
    
    html = f"""
    <div style="display: flex; gap: 4px; align-items: center;">
        <!-- Copy Button -->
        <button class="copy-button" onclick="{copy_func}()" title="Copy message content">
            📋
        </button>
        
        <!-- Thumbs Up Button -->
        <button class="{thumbs_up_class}" onclick="{thumbs_up_func}()" title="Thumbs up">
            ⌃
        </button>
        
        <!-- Thumbs Down Button -->
        <button class="{thumbs_down_class}" onclick="{thumbs_down_func}()" title="Thumbs down">
            ˅
        </button>
        
        <!-- Edit Button -->
        <button class="action-button" onclick="{edit_func}()" title="Edit message">
            ✎
        </button>
    </div>
    
    <script>
        // Copy message content
        function {copy_func}() {{
            const content = `{message_id}`;  // We'll pass the actual content
            navigator.clipboard.writeText(content).then(() => {{
                // Flash feedback
                const btn = event.target;
                const original = btn.innerHTML;
                btn.innerHTML = '✅';
                setTimeout(() => btn.innerHTML = original, 1000);
            }}).catch(err => console.error('Copy failed:', err));
        }}
        
        // Thumbs up
        function {thumbs_up_func}() {{
            const url = new URL(window.location);
            url.searchParams.set('button_action', 'true');
            url.searchParams.set('type', 'feedback');
            url.searchParams.set('action', 'thumbs_up');
            url.searchParams.set('messageId', '{message_id}');
            url.searchParams.set('idx', '{idx}');
            window.location.href = url.toString();
        }}
        
        // Thumbs down  
        function {thumbs_down_func}() {{
            const url = new URL(window.location);
            url.searchParams.set('button_action', 'true');
            url.searchParams.set('type', 'feedback');
            url.searchParams.set('action', 'thumbs_down');
            url.searchParams.set('messageId', '{message_id}');
            url.searchParams.set('idx', '{idx}');
            window.location.href = url.toString();
        }}
        
        // Edit message
        function {edit_func}() {{
            const url = new URL(window.location);
            url.searchParams.set('button_action', 'true');
            url.searchParams.set('type', 'edit');
            url.searchParams.set('action', 'edit_message');
            url.searchParams.set('messageId', '{message_id}');
            url.searchParams.set('idx', '{idx}');
            window.location.href = url.toString();
        }}
    </script>
    """
    
    return html

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

def update_dataframe_mapping(sess, sql: str, dataframe_key: str) -> tuple[str, str]:
    """
    Extract table name from SQL and update the latest_dataframes mapping.
    
    Returns a tuple of (table_name, dataframe_name):
    - table_name: The base name from the SQL 'FROM' clause (e.g., 'dim_users').
      This is used for the 'table' attribute in <dataframe> tags and for chart lookups.
      It should *not* contain a numeric suffix.
    - dataframe_name: A unique identifier for the dataframe in the session,
      including a suffix (e.g., 'dim_users_1'). This is used for the 'name'
      attribute in <dataframe> tags and as the key in st.session_state.
    """
    # Extract table name from SQL. If no FROM clause, default to "metadata".
    table_match = re.search(r"FROM\s+(\w+(?:\.\w+)?)", sql, re.IGNORECASE)
    table_name = table_match.group(1) if table_match else "metadata"
    
    # Update table counter and latest_dataframes mapping
    if table_name not in sess.table_counters:
        sess.table_counters[table_name] = 1
    else:
        sess.table_counters[table_name] += 1
    
    dataframe_name = f"{table_name}_{sess.table_counters[table_name]}"
    sess.latest_dataframes[table_name] = dataframe_name
    return table_name, dataframe_name

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

def _reload_and_rerun(sess, metadata_db):
    """Helper to reload conversation state from DB and trigger a rerun."""
    sess.db_messages = metadata_db.load_messages(sess.current_conversation_id)
    sess.llm_handler.messages = []
    for msg in sess.db_messages:
        sess.llm_handler.add_message(msg["role"], msg["content"])
    st.rerun()

def handle_button_message(message_data, metadata_db):
    """Handle button click messages from HTML buttons"""
    try:
        if message_data.get('type') == 'feedback':
            message_id = message_data.get('messageId')
            action = message_data.get('action')
            
            if action == 'thumbs_up':
                # Toggle thumbs up: 1 if not selected, 0 if already selected
                current_score = metadata_db.get_feedback_score(message_id) or 0
                new_score = 0 if current_score == 1 else 1
                metadata_db.update_feedback_score(message_id, new_score)
                _reload_and_rerun(st.session_state, metadata_db)
                
            elif action == 'thumbs_down':
                # Toggle thumbs down: -1 if not selected, 0 if already selected
                current_score = metadata_db.get_feedback_score(message_id) or 0
                new_score = 0 if current_score == -1 else -1
                metadata_db.update_feedback_score(message_id, new_score)
                _reload_and_rerun(st.session_state, metadata_db)
                
        elif message_data.get('type') == 'edit':
            message_id = message_data.get('messageId')
            st.session_state.editing_message_id = message_id
            st.rerun()
            
    except Exception as e:
        st.error(f"Error handling button click: {str(e)}")
        print(f"Button message error: {e}")

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

def display_message(idx, message, sess, analytic_db, metadata_db):
    """Display a chat message with its components or an editor."""
    is_editing = sess.editing_message_id is not None and sess.editing_message_id == message.get('id')

    with st.chat_message(message["role"], avatar=avatars.get(message["role"])):
        if is_editing:
            # Render the editor UI
            new_content = st.text_area(
                "Edit message",
                value=message['content'],
                height=250,
                key=f"editor_textarea_{message['id']}"
            )

            # Define columns for action buttons
            num_buttons = 4 if message['role'] == ASSISTANT_ROLE else 3
            cols = st.columns(num_buttons)

            # Cancel button (common to both roles)
            if cols[0].button("Cancel", key=f"cancel_{message['id']}"):
                sess.editing_message_id = None
                st.rerun()

            # Save Only button (common to both roles)
            if cols[1].button("Save Only", key=f"save_only_{message['id']}"):
                metadata_db.update_message_content(message['id'], new_content)
                sess.editing_message_id = None
                _reload_and_rerun(sess, metadata_db)
            
            # Role-specific buttons
            if message['role'] == USER_ROLE:
                if cols[2].button("Save & Regenerate", key=f"save_regen_{message['id']}"):
                    metadata_db.update_message_content(message['id'], new_content)
                    metadata_db.delete_subsequent_messages(sess.current_conversation_id, message['id'])
                    sess.pending_response = True
                    sess.editing_message_id = None
                    _reload_and_rerun(sess, metadata_db)
            elif message['role'] == ASSISTANT_ROLE:
                if cols[2].button("Save & Rerun", key=f"save_rerun_{message['id']}"):
                    metadata_db.update_message_content(message['id'], new_content)
                    metadata_db.delete_subsequent_messages(sess.current_conversation_id, message['id'])
                    
                    # After deleting, the edited message is now the last one.
                    # We re-parse it to set pending actions.
                    edited_msg_elements = get_elements(new_content)
                    sess.pending_sql = list(enumerate(edited_msg_elements.get("sql", [])))
                    sess.pending_chart = list(enumerate(edited_msg_elements.get("chart", [])))
                    sess.pending_python = list(enumerate(edited_msg_elements.get("python", [])))
                    
                    sess.editing_message_id = None
                    _reload_and_rerun(sess, metadata_db)

                if cols[3].button("Save & Complete", key=f"save_complete_{message['id']}"):
                    metadata_db.update_message_content(message['id'], new_content)
                    metadata_db.delete_subsequent_messages(sess.current_conversation_id, message['id'])
                    sess.pending_completion = message['id']
                    sess.editing_message_id = None
                    _reload_and_rerun(sess, metadata_db)
        else:
            # Render the read-only view
            # In dev mode, show raw content and trim button in columns
            if sess.dev_mode:
                # Ensure all messages have an ID, critical for editing
                assert 'id' in message, f"Message at index {idx} is missing an ID."

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
                            message_id = message.get('id')
                            if message_id:
                                if metadata_db.trim_conversation_after_message(sess.current_conversation_id, message_id):
                                    # Reload conversation
                                    sess.db_messages = metadata_db.load_messages(sess.current_conversation_id)
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
                
                if message["role"] == ASSISTANT_ROLE and "reasoning" in msg:
                    for item in msg["reasoning"]:
                        with st.expander("Reasoning", expanded=False):
                            st.markdown(item["content"])
                
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

                if "chart" in msg: # Display raw chart configuration
                    for item in msg["chart"]:
                        with st.expander(title_text(item["content"]), expanded=False):
                            st.code(item["content"], language="yaml")

                if "dataframe" in msg:
                    for item in msg["dataframe"]:
                        display_dataframe_item(item, idx, sess, analytic_db)

                if "figure" in msg:
                    for item in msg["figure"]:
                        display_figure_item(item, idx, sess, analytic_db)

                if "metadata" in msg:
                    for item in msg["metadata"]:
                        with st.expander("Metadata", expanded=True):
                            st.code(item["content"])

                if "error" in msg:
                    for item in msg["error"]:
                        with st.expander(title_text(item["content"]), expanded=False):
                            st.code(item["content"])
                
                # Create a row of action buttons (👍, 👎, ✏️) laid out with Streamlit columns.
                cols = st.columns([0.1, 0.1, 0.1, 1])

                # --- THUMBS UP ---
                with cols[0]:
                    up_type = "primary" if message.get('feedback_score', 0) == 1 else "secondary"
                    if st.button("˄", key=f"thumbs_up_{idx}", help="Thumbs up", type=up_type):
                        new_score = 0 if message.get('feedback_score', 0) == 1 else 1
                        metadata_db.update_feedback_score(message['id'], new_score)
                        _reload_and_rerun(sess, metadata_db)

                # --- THUMBS DOWN ---
                with cols[1]:
                    down_type = "primary" if message.get('feedback_score', 0) == -1 else "secondary"
                    if st.button("˅", key=f"thumbs_down_{idx}", help="Thumbs down", type=down_type):
                        new_score = 0 if message.get('feedback_score', 0) == -1 else -1
                        metadata_db.update_feedback_score(message['id'], new_score)
                        _reload_and_rerun(sess, metadata_db)

                # --- EDIT ---
                with cols[2]:
                    if st.button("✎", key=f"edit_{idx}", help="Edit message", type="secondary"):
                        sess.editing_message_id = message.get('id')
                        st.rerun()

def _format_dataframe_preview_for_llm(df: pd.DataFrame) -> list[str]:
    """Formats a DataFrame into a TSV-like list of strings for LLM preview, with head/tail truncation."""
    N_ROWS_HEAD_TAIL = 5
    THRESHOLD_FOR_HEAD_TAIL_DISPLAY = 2 * N_ROWS_HEAD_TAIL + 10

    def format_value(val):
        if isinstance(val, float):
            return f"{val:.4f}"
        return str(val)

    if df.empty:
        if not list(df.columns):  # No columns (e.g., from pd.DataFrame())
            return ["(Query returned no columns and no rows)"]
        else:  # Has columns, but no rows
            return ["\\t".join(df.columns), "(Query returned no rows)"]
    
    tsv_lines = ["\\t".join(df.columns)]
    if len(df) > THRESHOLD_FOR_HEAD_TAIL_DISPLAY:
        # Head
        for _, row in df.head(N_ROWS_HEAD_TAIL).iterrows():
            tsv_lines.append("\\t".join(format_value(val) for val in row))
        
        omitted_count = len(df) - 2 * N_ROWS_HEAD_TAIL
        tsv_lines.append(f"... {omitted_count} rows omitted ...")
        
        # Tail
        for _, row in df.tail(N_ROWS_HEAD_TAIL).iterrows():
            tsv_lines.append("\\t".join(format_value(val) for val in row))
    else:  # Show all rows if it's short enough
        for _, row in df.iterrows():
            tsv_lines.append("\\t".join(format_value(val) for val in row))
    return tsv_lines

def has_continuation_proposal(message_content: str) -> bool:
    """Check if message content contains the AI continuation proposal tag."""
    return f"<{AI_PROPOSES_CONTINUATION_TAG}/>" in message_content or f"<{AI_PROPOSES_CONTINUATION_TAG} />" in message_content

def find_continuation_proposal(messages):
    """Check if the most recent ASSISTANT message contains a continuation tag."""
    for message in reversed(messages):
        if message["role"] == ASSISTANT_ROLE:
            # Found the most recent assistant message
            return has_continuation_proposal(message["content"])
    return False

def has_error_tag(message_content: str) -> bool:
    """Check if message content contains an <error> tag."""
    # The get_elements function in parsing.py will extract content within <error>...</error>
    # So we just need to check for the presence of the tag itself.
    return "<error>" in message_content.lower() # Check for the opening tag, case-insensitive

def process_sql_query(sql_tuple, analytic_db):
    """Process an SQL query and store results as a dataframe"""
    sess = st.session_state
    sql_idx, sql_item = sql_tuple
    sql = sql_item["content"]
    
    print(f"DEBUG - Processing SQL query: {sql[:100]}...")
    msg_idx = len(sess.db_messages) - 1
    
    # Check if analytic database is available
    if not analytic_db:
        error_msg = "No analytic database configured. Please configure a database connection to run SQL queries."
        print(f"ERROR - {error_msg}")
        conv_manager.add_message(role=USER_ROLE, content=f"<error>\n{error_msg}\n</error>\n")
        return True
    
    # Execute query and handle errors
    print(f"DEBUG - Executing SQL query with msg_idx={msg_idx}, sql_idx={sql_idx}")
    df, err = analytic_db.execute_query(sql)
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
    table_name, dataframe_name = update_dataframe_mapping(sess, sql, None)
    
    # Store dataframe in session state
    dataframe_key = f"dataframe_{dataframe_name}"
    sess[dataframe_key] = df
    
    # Format preview for display
    tsv_lines = _format_dataframe_preview_for_llm(df)
    
    # Create and add dataframe message
    # IMPORTANT: The `table` attribute must be the base table name from the SQL
    # `FROM` clause, while the `name` attribute is the unique suffixed name.
    content = f'<dataframe name="{dataframe_name}" table="{table_name}" sql_msg_idx="{msg_idx}" sql_tag_idx="{sql_idx}" >\n'
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
        tsv_lines = _format_dataframe_preview_for_llm(result.dataframe)
        
        # Create dataframe message
        # IMPORTANT: The `table` attribute is the base name for the output,
        # while `name` is the unique suffixed name for session state.
        content = f'<dataframe name="{dataframe_name}" table="{base_name}" python_msg_idx="{msg_idx}" python_tag_idx="{python_idx}" >\n'
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

def cleanup_resources():
    """Cleanup function to be called on exit"""
    print("DEBUG - Cleaning up resources...")
    sess = st.session_state
    if hasattr(sess, 'analytic_db') and sess.analytic_db:
        sess.analytic_db.close()
        print("DEBUG - Closed analytic database connection")
    if hasattr(sess, 'metadata_db') and sess.metadata_db:
        # Commit any pending transactions and checkpoint WAL before closing
        try:
            sess.metadata_db.commit_and_checkpoint()
            print("DEBUG - Committed and checkpointed metadata database")
        except Exception as e:
            print(f"DEBUG - Error committing/checkpointing metadata database: {e}")
        sess.metadata_db.conn.close()
        print("DEBUG - Closed metadata database connection")

def main():
    sess = st.session_state

    # Initialize environment and load settings.env on first run.
    # This must happen before st.set_page_config.
    if 'config_base_path' not in sess:
        config_base_env_var = os.environ.get("LISTPET_BASE")
        if not config_base_env_var:
            st.error("LISTPET_BASE environment variable is required")
            st.stop()
        
        sess.config_base_path = os.path.abspath(os.path.expanduser(config_base_env_var))
        
        settings_path = os.path.join(sess.config_base_path, "settings.env")
        if os.path.exists(settings_path):
            load_dotenv(dotenv_path=settings_path)
            print(f"DEBUG - Loaded environment variables from: {settings_path}")
        else:
            st.error(f"settings.env not found at: {settings_path}")
            st.stop()

    # Get app display settings from environment or use defaults.
    # These are loaded from settings.env in the initialization block below.
    app_title = os.environ.get("APP_TITLE", "List Pet")
    app_caption = os.environ.get("APP_CAPTION", "Your friendly SQL assistant")
    app_icon_setting = os.environ.get("APP_ICON", "🐾")

    # The page config must be the first Streamlit command.
    # We will determine the icon (emoji or path) before setting it.
    # The actual loading of the .env file happens in the one-time init block.
    # If this is the first run and the .env hasn't been loaded, it will use defaults,
    # and a rerun will be triggered by the init, which will then have the env vars.
    st.set_page_config(page_title=app_title, page_icon=app_icon_setting, layout="wide")

    # Register cleanup on exit, but only once per session
    if 'cleanup_registered' not in sess:
        # The signal-based cleanup is not compatible with Streamlit's threading model.
        # We rely on atexit for graceful shutdowns and periodic checkpointing
        # to minimize data loss on abrupt termination.
        
        # Register with atexit for normal exits.
        atexit.register(cleanup_resources)
        
        sess.cleanup_registered = True
        print("DEBUG - atexit cleanup handler registered.")
    
    global conv_manager # To assign to the global variable from session state

    if 'app_initialized' not in sess:
        print("DEBUG - Performing one-time application initialization...")

        # The environment and config path are now set up before this block.
        # We can proceed directly to initializing database connections.
        print(f"DEBUG - Using LISTPET_BASE: {sess.config_base_path}")

        # 3. Create database instances
        if 'metadata_db' not in sess:
            conversation_file = os.environ.get("DUCKDB_CONVERSATION_FILE")
            if not conversation_file:
                st.error("DUCKDB_CONVERSATION_FILE environment variable is required")
                st.stop()
            
            conversation_path = os.path.join(sess.config_base_path, conversation_file)
            os.makedirs(os.path.dirname(conversation_path), exist_ok=True)
            
            sess.metadata_db = MetadataDatabase(conversation_path)
            sess.metadata_db.initialize_schema()
            print(f"DEBUG - MetadataDatabase initialized: {conversation_path}")

        if 'analytic_db' not in sess:
            # Get database type from settings
            db_type = os.environ.get("ANALYTIC_DATABASE")
            if not db_type:
                st.error("ANALYTIC_DATABASE environment variable is required in settings.env")
                st.stop()
                
            if db_type not in ["duckdb", "postgresql"]:
                st.error(f"ANALYTIC_DATABASE must be either 'duckdb' or 'postgresql', got: {db_type}")
                st.stop()
            
            if db_type == "postgresql":
                postgres_conn_str = os.environ.get("POSTGRES_CONN_STR")
                if not postgres_conn_str:
                    st.error("POSTGRES_CONN_STR environment variable is required when ANALYTIC_DATABASE=postgresql")
                    st.stop()
                sess.analytic_db = create_analytic_database("postgresql", postgres_conn_str=postgres_conn_str)
                print("DEBUG - Using PostgreSQL for analytic queries")
            else:  # duckdb
                analytic_file = os.environ.get("DUCKDB_ANALYTIC_FILE")
                if not analytic_file:
                    st.error("DUCKDB_ANALYTIC_FILE environment variable is required when ANALYTIC_DATABASE=duckdb")
                    st.stop()
                analytic_path = os.path.join(sess.config_base_path, analytic_file)
                sess.analytic_db = create_analytic_database("duckdb", duckdb_path=analytic_path)
                print(f"DEBUG - Using DuckDB for analytic queries: {analytic_path}")

        if 'conv_manager' not in sess:
            sess.conv_manager = ConversationManager(sess.metadata_db)
            sess.conv_manager.init_session_state() # Initializes sess.db_messages, etc.
            print("DEBUG - ConversationManager initialized.")

        sess.app_initialized = True
        print("DEBUG - One-time application initialization complete.")

    # Retrieve/assign core objects from session state for use in this run
    # This ensures that global conv_manager and local analytic_db_instance point to the persistent session objects
    conv_manager = sess.conv_manager 
    analytic_db_instance = sess.analytic_db

    # Add CSS styles with better injection method
    # Apply styles in the right order and ensure they're applied on every run
    css_styles = [
        CODE_WRAP_STYLE,
        CONVERSATION_BUTTON_STYLE,
        CONTINUE_AI_PLAN_BUTTON_STYLE,
        ACTION_BUTTON_STYLES,
        SUBTLE_ACTION_BUTTON_STYLE
    ]
    
    # Use components.html for more reliable CSS injection
    combined_css = "".join(css_styles)
    st.markdown(combined_css, unsafe_allow_html=True)
    
    # Also inject our action button styles at the page level
    st.markdown(ACTION_BUTTON_STYLES, unsafe_allow_html=True)
    

    


    
    # Render UI
    with st.sidebar:
        sess.conv_manager.render_sidebar() # Use session state instance directly
        st.divider()
        if st.button("🛑 Cleanup and Exit", type="secondary"):
            print("DEBUG - Cleanup button pressed")
            cleanup_resources()
            st.stop()
    
    # Determine icon for display in the title
    title_icon_path = None
    title_icon_emoji = app_icon_setting
    if 'config_base_path' in sess and app_icon_setting != "🐾":
        potential_icon_path = os.path.join(sess.config_base_path, app_icon_setting)
        if os.path.exists(potential_icon_path):
            title_icon_path = potential_icon_path
            
    # Display title with icon and caption
    if title_icon_path:
        try:
            # Read image and encode in base64
            with open(title_icon_path, "rb") as f:
                image_bytes = f.read()
            encoded = base64.b64encode(image_bytes).decode()

            # Use HTML with flexbox for better alignment control.
            # `align-items: flex-end` aligns items to the bottom of the container.
            # The h1 styling is adjusted to better align with the image bottom.
            st.markdown(f"""
                <div style="display: flex; align-items: flex-end; gap: 12px;">
                    <img src="data:image/png;base64,{encoded}" width="48">
                    <h1 style="margin: 0; padding-bottom: 0.1em;">{app_title}</h1>
                </div>
                """, unsafe_allow_html=True)

        except (FileNotFoundError, IsADirectoryError):
            # Fallback if icon path is invalid
            st.error(f"Icon file not found or is a directory: {title_icon_path}")
            st.title(f"{title_icon_emoji} {app_title}") # Fallback
    else:
        st.title(f"{title_icon_emoji} {app_title}")

    st.caption(app_caption)

    # Display chat messages
    for idx, message in enumerate(sess.db_messages):
        # Skip system message (first message) if not in dev mode
        if idx == 0 and not sess.dev_mode:
            continue
        display_message(idx, message, sess, analytic_db_instance, sess.metadata_db) # Pass both databases

    # Check if the last AI message proposes continuation
    show_continue_ai_plan_button = False
    show_fix_error_button = False

    if sess.db_messages:
        last_message = sess.db_messages[-1]
        last_message_content = last_message["content"]
                
        # Check for continuation proposal in any recent assistant message
        found_continuation = find_continuation_proposal(sess.db_messages)
        
        if found_continuation:
            show_continue_ai_plan_button = True
            print("DEBUG - Setting show_continue_ai_plan_button to True")
        # Check for error tag in the last message, regardless of role, 
        # as system-generated errors are added as USER_ROLE.
        elif has_error_tag(last_message_content):
            show_fix_error_button = True

    # Process pending items
    if sess.pending_python and sess.pending_python[0]:
        python_tuple = sess.pending_python.pop(0)
        if process_python_code(python_tuple):
            st.rerun()

    if sess.pending_sql and sess.pending_sql[0]:
        sql_tuple = sess.pending_sql.pop(0)
        if process_sql_query(sql_tuple, analytic_db_instance): # Pass session-managed analytic_db_instance
            st.rerun()

    if sess.pending_chart and sess.pending_chart[0]:
        chart_tuple = sess.pending_chart.pop(0)
        if process_chart_request(chart_tuple):
            st.rerun()

    if 'pending_completion' in sess and sess.pending_completion:
        message_id_to_complete = sess.pending_completion
        sess.pending_completion = None  # Reset flag

        edited_message = next((m for m in sess.db_messages if m['id'] == message_id_to_complete), None)

        if not edited_message:
            st.error(f"Could not find message {message_id_to_complete} to complete.")
        else:
            # Rebuild LLM history up to the message before the edited one
            sess.llm_handler.messages = []
            for msg in sess.db_messages:
                if msg['id'] < message_id_to_complete:
                    sess.llm_handler.add_message(msg['role'], msg['content'])

            # Extract reasoning to use as the prompt for completion
            edited_content = edited_message['content']
            msg_elements = get_elements(edited_content)
            # Use reasoning content, or the full content if no reasoning tag
            reasoning_content = msg_elements.get("reasoning", [{}])[0].get("content")
            if reasoning_content:
                completion_prompt = f"<reasoning>\n{reasoning_content}\n</reasoning>"
            else:
                completion_prompt = edited_content

            sess.llm_handler.add_message(ASSISTANT_ROLE, completion_prompt)

            # Generate the rest of the message
            completion_result = sess.llm_handler.generate_response()

            if completion_result:
                # Combine and update the original message
                final_content = f"{completion_prompt}\n{completion_result}"
                sess.metadata_db.update_message_content(message_id_to_complete, final_content)

                # After updating, parse the new content for any pending actions
                final_elements = get_elements(final_content)
                sess.pending_sql = list(enumerate(final_elements.get("sql", [])))
                sess.pending_chart = list(enumerate(final_elements.get("chart", [])))
                sess.pending_python = list(enumerate(final_elements.get("python", [])))
            else:
                st.error("Failed to generate completion from LLM.")

            # Reload and show the final state
            _reload_and_rerun(sess, sess.metadata_db)

    if sess.pending_response:
        if generate_llm_response():
            st.rerun()
        
    # Conditionally display the buttons
    # The styling for these buttons is expected to be in ui_styles.py
    # and applied globally via st.markdown.
    # We use the same column structure for layout consistency.
    if show_continue_ai_plan_button or show_fix_error_button:
        container = st.container()
        with container:
            button_cols = st.columns([3, 7]) # Adjust ratio as needed
            with button_cols[0]:
                if show_continue_ai_plan_button:
                    if st.button("Continue with AI's plan?", key="continue_ai_plan_button", type="primary"):
                        approval_message = f"<{USER_APPROVES_CONTINUATION_TAG}/>"
                        sess.conv_manager.add_message(role=USER_ROLE, content=approval_message)
                        sess.pending_response = True 
                        st.rerun()
                elif show_fix_error_button:
                    if st.button("Ask AI to fix this?", key="fix_error_button", type="primary"):
                        fix_request_message = f"<{USER_REQUESTS_ERROR_FIX_TAG}/>"
                        sess.conv_manager.add_message(role=USER_ROLE, content=fix_request_message)
                        sess.pending_response = True
                        st.rerun()

    # Process user input    
    user_chat_input = st.chat_input("Type your message...") # Renamed variable
    if user_chat_input:
        # Process SQL syntax
        processed_input = user_chat_input
        if re.match(SQL_REGEX, user_chat_input.strip(), re.IGNORECASE):
            processed_input = "<sql>\n" + user_chat_input + "\n</sql>\n"
        
        sess.conv_manager.add_message(role=USER_ROLE, content=processed_input) # Use session state instance
             
        # Check for SQL in input
        msg = get_elements(processed_input)
        if msg.get("sql"):
            sess.pending_sql = list(enumerate(msg.get("sql", [])))
        else:
            sess.pending_response = True
            
        st.rerun()

