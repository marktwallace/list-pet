import streamlit as st
import os
import re
import json
import pandas as pd
from datetime import datetime
import plotly.express as px
import traceback

from .chat import ChatEngine
from .database import Database
from .message_manager import get_message_manager
from .parse import parse_markup
from .plotting import get_plotter
from .mapping import get_mapper
from .sql_utils import is_sql_query, extract_table_name_from_sql, is_command, handle_command
from .response_processor import process_sql_blocks, prepare_plot_error_message, prepare_map_error_message, prepare_no_data_error_message
from .constants import ASSISTANT_ROLE, USER_ROLE, USER_ACTOR, DATABASE_ACTOR

def handle_user_input(user_input):
    """Process user input, handle commands and SQL queries, and return if app should rerun."""
    if not user_input:
        return False
    
    # Get message manager
    message_manager = get_message_manager()
    
    # Check if input is a command
    if is_command(user_input):
        try:
            result = handle_command(user_input)
            message_manager.add_system_message(f"Command result: {result}")
            return True
        except Exception as e:
            error_message = f"Error executing command: {str(e)}"
            print(f"ERROR: {error_message}")
            message_manager.add_system_message(error_message, is_error=True)
            return True
    
    # Add user message
    message_manager.add_user_message(user_input)
    
    # Check if input is an SQL query
    if is_sql_query(user_input):
        print(f"DEBUG - Executing SQL query: {user_input}")
        
        try:
            # Execute SQL query
            result, is_error, df = message_manager.execute_sql(user_input)
            
            # Log the result
            print(f"DEBUG - SQL result: error={is_error}, df_shape={df.shape if df is not None else None}")
            
            # Handle specific SQL commands
            if not is_error:
                # For CREATE TABLE, ALTER TABLE, etc. - update the schema
                if re.search(r'^\s*(CREATE|ALTER)\s+TABLE', user_input, re.IGNORECASE):
                    print("DEBUG - Updating schema after table creation/alteration")
                    db = Database()
                    db.update_schema_info()
                
                # For INSERT INTO - update the row counts
                if re.search(r'^\s*INSERT\s+INTO', user_input, re.IGNORECASE):
                    print("DEBUG - Updating row counts after data insertion")
                    db = Database()
                    db.update_row_counts()
            
            # Add database message with the result
            if df is not None and not is_error:
                message_manager.add_database_message(result, dataframe=df, query_text=user_input)
            else:
                message_manager.add_database_message(result, is_error=is_error)
            
            return True
            
        except Exception as e:
            error_message = f"Error executing SQL: {str(e)}"
            print(f"ERROR: {error_message}")
            print(f"TRACEBACK: {traceback.format_exc()}")
            message_manager.add_database_message(error_message, is_error=True)
            return True
    
    return False

def handle_ai_response(response, chat_engine, db, retry_count=0):
    """Process AI response, execute SQL blocks, and handle errors."""
    message_manager = get_message_manager()
    
    try:
        # Parse the response for SQL blocks
        parsed_response, sql_blocks = process_sql_blocks(response)
        
        # Also parse the response for plot specifications
        parsed = parse_markup(response)
        plot_specs = parsed.get("plot", [])
        
        # Add the assistant message
        message_id = message_manager.add_assistant_message(parsed_response)
        
        # Process each SQL block
        for sql_block in sql_blocks:
            sql_query = sql_block["sql"]
            print(f"DEBUG - Executing SQL from AI response: {sql_query}")
            
            # Execute the SQL query
            result, is_error, df = message_manager.execute_sql(sql_query)
            
            # Check for table creation or modification
            if not is_error:
                # For CREATE TABLE, ALTER TABLE, etc. - update the schema
                if re.search(r'^\s*(CREATE|ALTER)\s+TABLE', sql_query, re.IGNORECASE):
                    print("DEBUG - Updating schema after table creation/alteration")
                    db.update_schema_info()
                
                # For INSERT INTO - update the row counts
                if re.search(r'^\s*INSERT\s+INTO', sql_query, re.IGNORECASE):
                    print("DEBUG - Updating row counts after data insertion")
                    db.update_row_counts()
            
            # Add database message with the result
            if df is not None and not is_error:
                message_manager.add_database_message(result, dataframe=df, query_text=sql_query)
            else:
                message_manager.add_database_message(result, is_error=is_error)
            
            # Check for visualization requests
            if sql_block.get("plot_spec") and df is not None and not is_error:
                try:
                    from .plotting import get_plotter
                    plotter = get_plotter()
                    fig, error = plotter.create_plot(sql_block["plot_spec"], df)
                    
                    if error:
                        error_message = prepare_plot_error_message(error)
                        message_manager.add_database_message(error_message, is_error=True)
                    else:
                        message_manager.add_plot_message(df, fig, message_id, sql_block["plot_spec"], sql_query)
                except Exception as e:
                    error_message = f"Error creating plot: {str(e)}"
                    print(f"ERROR: {error_message}")
                    print(f"TRACEBACK: {traceback.format_exc()}")
                    message_manager.add_database_message(error_message, is_error=True)
            
            # If there are plot specs but they're not associated with SQL blocks, try to associate them
            elif df is not None and not is_error and plot_specs:
                for plot_spec in plot_specs:
                    try:
                        from .plotting import get_plotter
                        plotter = get_plotter()
                        fig, error = plotter.create_plot(plot_spec, df)
                        
                        if error:
                            error_message = prepare_plot_error_message(error)
                            message_manager.add_database_message(error_message, is_error=True)
                        else:
                            message_manager.add_plot_message(df, fig, message_id, plot_spec, sql_query)
                        
                        # Remove this plot spec so we don't process it again
                        plot_specs.remove(plot_spec)
                        break
                    except Exception as e:
                        error_message = f"Error creating plot: {str(e)}"
                        print(f"ERROR: {error_message}")
                        print(f"TRACEBACK: {traceback.format_exc()}")
                        message_manager.add_database_message(error_message, is_error=True)
            
            # Check for map visualization requests
            if sql_block.get("map_spec") and df is not None and not is_error:
                try:
                    from .mapping import get_mapper
                    mapper = get_mapper()
                    fig, error = mapper.create_map(sql_block["map_spec"], df)
                    
                    if error:
                        error_message = prepare_map_error_message(error)
                        message_manager.add_database_message(error_message, is_error=True)
                    else:
                        message_manager.add_map_message(df, fig, message_id, sql_block["map_spec"], sql_query)
                except Exception as e:
                    error_message = f"Error creating map: {str(e)}"
                    print(f"ERROR: {error_message}")
                    print(f"TRACEBACK: {traceback.format_exc()}")
                    message_manager.add_database_message(error_message, is_error=True)
    
    except Exception as e:
        error_message = f"Error processing response: {str(e)}"
        print(f"ERROR: {error_message}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        
        # If we haven't retried too many times, try again with a simpler response
        if retry_count < 2:
            print(f"DEBUG - Retrying with simpler response (attempt {retry_count + 1})")
            try:
                # Generate a simpler response
                simpler_response = chat_engine.generate_fallback_response()
                handle_ai_response(simpler_response, chat_engine, db, retry_count + 1)
            except Exception as retry_error:
                error_message = f"Error generating fallback response: {str(retry_error)}"
                print(f"ERROR: {error_message}")
                message_manager.add_system_message("There was a problem generating a new response. Please try rephrasing your question.", is_error=True)
        else:
            message_manager.add_system_message("There was a problem generating a new response. Please try rephrasing your question.", is_error=True)

def generate_ai_response(chat_engine, db):
    """Generate and process AI response, including error handling."""
    message_manager = get_message_manager()
    
    try:
        with st.spinner("Thinking..."):
            # Get AI response
            response = chat_engine.generate_response(message_manager.get_messages())
            
            # Process the response
            handle_ai_response(response, chat_engine, db)
    except Exception as e:
        error_message = f"Error generating response: {str(e)}"
        print(f"ERROR: {error_message}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        message_manager.add_system_message(error_message, is_error=True)

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

def initialize_session_state():
    """Initialize session state variables if they don't exist."""
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        print("DEBUG - Initializing session state")
        
        # Initialize the message manager
        message_manager = get_message_manager()
        
        # Add welcome message if no messages exist
        if not message_manager.get_messages():
            welcome_message = """
            # 👋 Welcome to List Pet!
            
            I'm your friendly SQL assistant. I can help you:
            
            - Create and manage tables
            - Query your data
            - Visualize results with plots and maps
            - Explain SQL concepts
            
            Try asking me a question or typing an SQL query directly.
            """
            message_manager.add_assistant_message(welcome_message)

def main():
    """Main function to set up the Streamlit app."""
    # Set page config
    st.set_page_config(
        page_title="List Pet",
        page_icon="🐾",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state
    initialize_session_state()
    
    # Get message manager
    message_manager = get_message_manager()
    
    # Set up the chat interface
    st.title("🐾 List Pet")
    st.caption("Your friendly SQL assistant")
    
    # Display all messages in the conversation history
    messages = message_manager.get_messages()
    for message in messages:
        message_manager.display_message(message)
    
    # Handle user input if provided
    if user_input := st.chat_input("Type your question here...", key=f"chat_input_{len(message_manager.get_messages())}"):
        should_rerun = handle_user_input(user_input)
        if should_rerun:
            st.rerun()
        
        # Generate AI response if needed
        if not is_sql_query(user_input) and not is_command(user_input):
            # Initialize chat engine and database
            chat_engine = ChatEngine("gpt-4o-mini")
            db = Database()
            
            # Generate AI response
            generate_ai_response(chat_engine, db)
            st.rerun()
    
    # Add focus to chat input
    add_chat_input_focus()

if __name__ == "__main__":
    main()

