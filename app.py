import streamlit as st
import os
from chat import ChatEngine, get_chat_engine
from database import Database, get_database
from parse import parse_markup
import re
import pandas as pd

# Constants
ASSISTANT_ROLE = "Assistant"
USER_ROLE = "User"
USER_ACTOR = "User"
DATABASE_ACTOR = "DuckDB"

def format_sql_result(query: str, df: pd.DataFrame | None, error: str | None) -> str:
    """Format SQL results in a consistent way"""
    output = []
    output.append(f"SQL Query:")
    output.append(f"```sql\n{query}\n```")
    if error:
        output.append("Error:")
        output.append(f"```\n{error}\n```")
    elif df is not None:
        output.append("Result:")
        output.append("```\n" + df.to_string(index=False) + "\n```")
    return "\n".join(output)

def is_sql_query(text: str) -> bool:
    """Check if text is SQL (either explicit <sql> tag or common SQL patterns)"""
    text = text.strip()
    return text.startswith("<sql>") or bool(re.match(
        r"^\s*(SELECT|CREATE|DROP|ALTER|INSERT|DELETE|UPDATE|SHOW|DESCRIBE)\s+",
        text, re.IGNORECASE
    ))

def execute_sql(query: str, db: Database) -> tuple[str, bool]:
    """Execute SQL and return (formatted_result, had_error)"""
    df, error = db.execute_query(query)
    return format_sql_result(query, df, error), bool(error)

def display_message(message: dict):
    """Display a message in user-friendly format"""
    with st.chat_message(message["role"]):
        if message["role"] == ASSISTANT_ROLE:
            # For assistant messages, parse and display only display blocks
            parsed = parse_markup(message["content"])
            display_text = "\n\n".join(item["text"] for item in parsed.get("display", []))
            st.markdown(display_text)
        else:
            # For user/database messages, display as is
            st.markdown(message["content"])

def handle_message(message: str, chat_engine: ChatEngine, db: Database) -> None:
    """Process a message and update conversation state"""
    if is_sql_query(message):
        # Direct SQL execution
        result, had_error = execute_sql(message, db)
        # Store raw SQL and result
        sql_message = f"{DATABASE_ACTOR}:\n{result}"
        st.session_state.messages.append({"role": USER_ROLE, "content": sql_message})
        
        if had_error:
            # Let AI try to fix the error
            response = chat_engine.generate_response(st.session_state.messages)
            handle_ai_response(response, chat_engine, db)
    else:
        # Store raw user message
        st.session_state.messages.append({"role": USER_ROLE, "content": f"{USER_ACTOR}: {message}"})
        # Get AI response
        response = chat_engine.generate_response(st.session_state.messages)
        handle_ai_response(response, chat_engine, db)

def handle_ai_response(response: str, chat_engine: ChatEngine, db: Database, retry_count: int = 0) -> None:
    """Process AI response, executing any SQL and handling errors"""
    # Store complete AI response with all markup
    st.session_state.messages.append({"role": ASSISTANT_ROLE, "content": response})
    
    parsed = parse_markup(response)
    
    # Execute any SQL blocks
    had_error = False
    for block in parsed.get("sql", []):
        if query := block.get("query"):
            result, is_error = execute_sql(query, db)
            # Store SQL results
            st.session_state.messages.append({"role": USER_ROLE, "content": f"{DATABASE_ACTOR}:\n{result}"})
            had_error = had_error or is_error
    
    # If SQL error and haven't retried, let AI try again
    if had_error and retry_count == 0:
        new_response = chat_engine.generate_response(st.session_state.messages)
        handle_ai_response(new_response, chat_engine, db, retry_count + 1)

def main():
    st.title("🐇 List Pet")
    st.caption("📋 An AI Data Assistant")
    
    # Initialize state with complete first message including markup
    if "messages" not in st.session_state:
        st.session_state.messages = []
        with open('prompts/first.txt', 'r') as f:
            first_message = f.read()
        st.session_state.messages.append({"role": ASSISTANT_ROLE, "content": first_message})
    
    # Setup chat engine and database
    chat_engine = get_chat_engine("gpt-4o-mini")
    db = get_database()
    
    # Display conversation history with user-friendly formatting
    for message in st.session_state.messages:
        display_message(message)
    
    # Handle new input
    if user_input := st.chat_input("Type your question here..."):
        handle_message(user_input, chat_engine, db)
        st.rerun()

if __name__ == "__main__":
    main()
