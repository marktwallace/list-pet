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
from .sql_utils import is_sql_query, execute_sql, format_sql_label
from .response_processor import process_sql_blocks, prepare_plot_error_message, prepare_map_error_message, prepare_no_data_error_message
from .message_manager import get_message_manager

# Import command-related utilities and constants
from .commands import is_command, handle_command
from .constants import ASSISTANT_ROLE, USER_ROLE, USER_ACTOR, DATABASE_ACTOR

def display_message(message: dict):
    """Display a message in user-friendly format."""
    message_manager = get_message_manager()
    messages = message_manager.get_messages()
    
    with st.chat_message(message["role"]):
        if message["role"] == ASSISTANT_ROLE:
            parsed = parse_markup(message["content"])
            print("DEBUG - Display parsed message:", parsed)
            display_text = "\n\n".join(item["text"] for item in parsed.get("display", []))
            st.markdown(display_text)
        elif "figure" in message:
            try:
                plot_msg_id = message.get("plot_msg_id")
                if not plot_msg_id:
                    msg_idx = messages.index(message)
                    plot_idx = message.get("plot_index", 0)
                    plot_msg_id = f"stored_plot_{msg_idx}_{plot_idx}"
                st.plotly_chart(message["figure"], use_container_width=True, key=plot_msg_id)
            except Exception as e:
                st.error(f"Error displaying plot: {str(e)}")
                print(f"DEBUG - Plot display error: {str(e)}")
        elif "map_figure" in message:
            try:
                map_msg_id = message.get("map_msg_id")
                if not map_msg_id:
                    msg_idx = messages.index(message)
                    map_idx = message.get("map_index", 0)
                    map_msg_id = f"stored_map_{msg_idx}_{map_idx}"
                st.plotly_chart(message["map_figure"], use_container_width=True, key=map_msg_id)
            except Exception as e:
                st.error(f"Error displaying map: {str(e)}")
                print(f"DEBUG - Map display error: {str(e)}")
        else:
            content = message["content"]
            if content.startswith(f"{DATABASE_ACTOR}:"):
                import re
                sql_match = re.search(r"```(?:sql)?\s*\n?(.*?)\n?```", content, re.DOTALL)
                if sql_match:
                    sql_query = sql_match.group(1).strip()
                    with st.expander(format_sql_label(sql_query)):
                        st.markdown(f"```sql\n{sql_query}\n```")
                if "Error:" in content:
                    error_match = re.search(r"Error:.*?```(.*?)```", content, re.DOTALL)
                    if error_match:
                        st.markdown(f"```\n{error_match.group(1).strip()}\n```")
                else:
                    df = message.get("dataframe")
                    if df is not None:
                        st.dataframe(
                            df,
                            use_container_width=True,
                            hide_index=True,
                            column_config={ col: st.column_config.Column(width="auto") for col in df.columns }
                        )
            else:
                st.markdown(content)

def handle_ai_response(response: str, chat_engine: ChatEngine, db: Database, retry_count: int = 0) -> None:
    """Process AI response, executing any SQL and handling errors."""
    message_manager = get_message_manager()
    message_manager.add_assistant_message(response)
    
    parsed = parse_markup(response)
    print("DEBUG - Parsed response:", parsed)
    
    # Process SQL blocks
    sql_messages, had_error, last_df = process_sql_blocks(parsed, db)
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
            print("DEBUG - No dataframe available for visualization")
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
                    print(f"DEBUG - Plot creation error: {error}")
                    plot_error = prepare_plot_error_message(plot_spec, error, last_df)
                    message_manager.add_message(plot_error)
                elif fig:
                    message_manager.add_plot_message(last_df, fig, i)
                    print(f"DEBUG - Plot added to messages")
                else:
                    print("DEBUG - No figure and no error returned from create_plot")
            except Exception as e:
                error_msg = f"Error creating plot: {str(e)}"
                print(f"DEBUG - Plot error: {str(e)}")
                traceback_str = traceback.format_exc()
                print(f"DEBUG - Plot error traceback: {traceback_str}")
                plot_error = prepare_plot_error_message(plot_spec, error_msg, last_df)
                message_manager.add_message(plot_error)
    elif parsed.get("plot", []):
        print("DEBUG - Plot specifications found but no dataframe available")
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
                    print(f"DEBUG - Map creation error: {error}")
                    map_error = prepare_map_error_message(map_spec, error, last_df)
                    message_manager.add_message(map_error)
                elif fig:
                    message_manager.add_map_message(last_df, fig, i)
                    print(f"DEBUG - Map added to messages")
                else:
                    print("DEBUG - No figure and no error returned from create_map")
            except Exception as e:
                error_msg = f"Error creating map: {str(e)}"
                print(f"DEBUG - Map error: {str(e)}")
                traceback_str = traceback.format_exc()
                print(f"DEBUG - Map error traceback: {traceback_str}")
                map_error = prepare_map_error_message(map_spec, error_msg, last_df)
                message_manager.add_message(map_error)
    elif parsed.get("map", []):
        print("DEBUG - Map specifications found but no dataframe available")
        map_error = prepare_no_data_error_message()
        message_manager.add_message(map_error)
    
    if had_error and retry_count == 0:
        new_response = chat_engine.generate_response(message_manager.get_messages())
        handle_ai_response(new_response, chat_engine, db, retry_count + 1)

def handle_user_input(user_input: str, db: Database) -> bool:
    """Process user input, handling commands and SQL queries.
    
    Returns True if the app should rerun after processing.
    """
    message_manager = get_message_manager()
    
    is_cmd, cmd_type, cmd_label = is_command(user_input)
    if is_cmd:
        result = handle_command(cmd_type, cmd_label)
        with st.chat_message(USER_ROLE):
            st.markdown(f"{USER_ACTOR}: {user_input}")
        with st.expander("Command Output (not saved to conversation)", expanded=True):
            st.text(result)
        return False
    
    # Regular user input (not a command)
    with st.chat_message(USER_ROLE):
        st.markdown(f"{USER_ACTOR}: {user_input}")
    
    message_manager.add_user_message(user_input)
    
    if is_sql_query(user_input):
        result, had_error, df = execute_sql(user_input, db)
        message_manager.add_database_message(result, df)
    
    st.session_state.needs_ai_response = True
    return True

def generate_ai_response(chat_engine: ChatEngine, db: Database) -> None:
    """Generate and process AI response."""
    message_manager = get_message_manager()
    
    with st.spinner("Thinking..."):
        response = chat_engine.generate_response(message_manager.get_messages())
        handle_ai_response(response, chat_engine, db)
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

