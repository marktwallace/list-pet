import streamlit as st
import os
import re
import json
import pandas as pd
from datetime import datetime
import plotly.express as px

from .chat import ChatEngine, get_chat_engine
from .database import Database, get_database
from .parse import parse_markup
from .plotting import get_plotter
from .sql_utils import is_sql_query, execute_sql, format_sql_label

# Import command-related utilities and constants
from .commands import is_command, handle_command
from .constants import ASSISTANT_ROLE, USER_ROLE, USER_ACTOR, DATABASE_ACTOR

def display_message(message: dict):
    """Display a message in user-friendly format."""
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
                    msg_idx = st.session_state.messages.index(message)
                    plot_idx = message.get("plot_index", 0)
                    plot_msg_id = f"stored_plot_{msg_idx}_{plot_idx}"
                st.plotly_chart(message["figure"], use_container_width=True, key=plot_msg_id)
            except Exception as e:
                st.error(f"Error displaying plot: {str(e)}")
                print(f"DEBUG - Plot display error: {str(e)}")
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
    st.session_state.messages.append({"role": ASSISTANT_ROLE, "content": response})
    parsed = parse_markup(response)
    print("DEBUG - Parsed response:", parsed)
    
    last_df = None
    had_error = False
    for block in parsed.get("sql", []):
        if query := block.get("query"):
            result, is_error, df = execute_sql(query, db)
            sql_message = {"role": USER_ROLE, "content": f"{DATABASE_ACTOR}:\n{result}", "dataframe": df}
            st.session_state.messages.append(sql_message)
            had_error = had_error or is_error
            if df is not None:
                last_df = df
                print(f"DEBUG - SQL result dataframe: {df.shape}, columns: {df.columns.tolist()}")
    
    if last_df is not None and parsed.get("plot", []):
        print(f"DEBUG - Found {len(parsed.get('plot', []))} plot specifications to process")
        plotter = get_plotter()
        for i, plot_spec in enumerate(parsed.get("plot", [])):
            print(f"DEBUG - Processing plot {i+1}/{len(parsed.get('plot', []))}: {plot_spec}")
            try:
                fig, error = plotter.create_plot(plot_spec, last_df)
                if error:
                    print(f"DEBUG - Plot creation error: {error}")
                    plot_type = plot_spec.get('type', 'unknown')
                    error_content = f"{DATABASE_ACTOR}:\n\n**Error creating {plot_type} plot:**\n```\n{error}\n```\n\nPlot specification:\n```json\n{json.dumps(plot_spec, indent=2)}\n```"
                    plot_error = {"role": USER_ROLE, "content": error_content, "dataframe": last_df}
                    st.session_state.messages.append(plot_error)
                    with st.chat_message(USER_ROLE):
                        st.markdown(error_content)
                elif fig:
                    plot_msg_id = f"plot_{len(st.session_state.messages)}_{i}"
                    print(f"DEBUG - Plot created successfully with ID: {plot_msg_id}")
                    plot_message = {
                        "role": USER_ROLE, 
                        "content": f"{DATABASE_ACTOR}:\nPlot created successfully", 
                        "dataframe": last_df,
                        "figure": fig,
                        "plot_index": i,
                        "plot_msg_id": plot_msg_id
                    }
                    st.session_state.messages.append(plot_message)
                    st.plotly_chart(fig, use_container_width=True, key=plot_msg_id)
                    print(f"DEBUG - Plot displayed with key: {plot_msg_id}")
                else:
                    print("DEBUG - No figure and no error returned from create_plot")
            except Exception as e:
                error_msg = f"Error creating plot: {str(e)}"
                print(f"DEBUG - Plot error: {str(e)}")
                import traceback
                traceback_str = traceback.format_exc()
                print(f"DEBUG - Plot error traceback: {traceback_str}")
                plot_type = plot_spec.get('type', 'unknown')
                error_content = f"{DATABASE_ACTOR}:\n\n**Error creating {plot_type} plot:**\n```\n{error_msg}\n```\n\nPlot specification:\n```json\n{json.dumps(plot_spec, indent=2)}\n```"
                plot_error = {"role": USER_ROLE, "content": error_content, "dataframe": last_df}
                st.session_state.messages.append(plot_error)
                with st.chat_message(USER_ROLE):
                    st.markdown(error_content)
    elif parsed.get("plot", []):
        print("DEBUG - Plot specifications found but no dataframe available")
        error_content = f"{DATABASE_ACTOR}:\n\n**Error creating plot:**\n```\nNo data available for plotting. Please run a SQL query first.\n```"
        plot_error = {"role": USER_ROLE, "content": error_content}
        st.session_state.messages.append(plot_error)
        with st.chat_message(USER_ROLE):
            st.markdown(error_content)
    elif last_df is not None:
        print("DEBUG - Dataframe available but no plot specifications found")
    
    if had_error and retry_count == 0:
        new_response = chat_engine.generate_response(st.session_state.messages)
        handle_ai_response(new_response, chat_engine, db, retry_count + 1)

def handle_user_input(user_input: str, db: Database) -> bool:
    """Process user input, handling commands and SQL queries.
    
    Returns True if the app should rerun after processing.
    """
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
    st.session_state.messages.append({"role": USER_ROLE, "content": f"{USER_ACTOR}: {user_input}"})
    
    if is_sql_query(user_input):
        result, had_error, df = execute_sql(user_input, db)
        sql_message = {"role": USER_ROLE, "content": f"{DATABASE_ACTOR}:\n{result}", "dataframe": df}
        st.session_state.messages.append(sql_message)
    
    st.session_state.needs_ai_response = True
    return True

def generate_ai_response(chat_engine: ChatEngine, db: Database) -> None:
    """Generate and process AI response."""
    with st.chat_message(ASSISTANT_ROLE):
        with st.spinner("Thinking..."):
            response = chat_engine.generate_response(st.session_state.messages)
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
    if "messages" not in st.session_state:
        st.session_state.messages = []
        with open('prompts/first.txt', 'r') as f:
            first_message = f.read()
        st.session_state.messages.append({"role": ASSISTANT_ROLE, "content": first_message})
    
    if "needs_ai_response" not in st.session_state:
        st.session_state.needs_ai_response = False

def main():
    st.title("🐇 List Pet")
    st.caption("📋 An AI Data Assistant")
    
    initialize_session_state()
    
    chat_engine = get_chat_engine("gpt-4o-mini")
    db = get_database()
    
    # Display all messages in the conversation history
    for message in st.session_state.messages:
        display_message(message)
    
    # Handle user input if provided
    if user_input := st.chat_input("Type your question here...", key=f"chat_input_{len(st.session_state.messages)}"):
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
