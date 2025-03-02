import streamlit as st
import os
from chat import ChatEngine, get_chat_engine
from database import Database, get_database
from parse import parse_markup
import re
import pandas as pd

def format_sql_result(query: str, df: pd.DataFrame | None, error: str | None) -> str:
    """Format SQL results to match DuckDB CLI style"""
    output = [f"D {query}"]
    
    if error:
        output.append(f"Error: {error}")
    elif df is not None:
        # Convert DataFrame to CLI-style table
        table_str = df.to_string(index=False)
        output.append(table_str)
    else:
        output.append("Query executed successfully")
    
    return "\n".join(output)

def is_sql_query(query: str) -> bool:
    """Determine if a query is SQL based on patterns"""
    stripped_query = query.strip()
    
    # Check for explicit SQL markup
    if stripped_query.startswith("<sql>"):
        return True
    
    # Check for common SQL statement patterns
    sql_patterns = r"^\s*(SELECT\s+\*|SELECT\s+\w+|CREATE\s+TABLE|DROP\s+TABLE|ALTER\s+TABLE|INSERT\s+INTO|DELETE\s+FROM|UPDATE\s+\w+|SHOW\s+TABLES|DESCRIBE\s+\w+|EXPLAIN\s+\w+)\s*.*"
    return bool(re.match(sql_patterns, stripped_query, re.IGNORECASE))

def display_message(message: dict, show_internal: bool):
    """Display a single message in the chat history"""
    if message["display"]["role"] == "ai":
        if show_internal:
            with st.chat_message("internal"):
                st.markdown(message["internal"]["content"])
        # Only show display message if content is not None
        if message["display"]["content"] is not None:
            with st.chat_message(message["display"]["role"]):
                st.markdown(message["display"]["content"])
    else:
        with st.chat_message(message["display"]["role"]):
            st.markdown(message["display"]["content"])

def execute_sql(query: str, show_internal: bool, db: Database):
    """Execute SQL and show results if needed"""
    df, error = db.execute_query(query)
    result_text = format_sql_result(query, df, error)
    
    if show_internal:
        with st.chat_message("internal"):
            st.markdown(f"```\nDuckDB:\n{result_text}\n```")
    
    return result_text, error

def handle_sql_query(query: str, show_internal: bool, db: Database):
    """Handle direct SQL query from user"""
    with st.chat_message("user"):
        st.markdown(f"```sql\n{query}\n```")
    
    result_text, error = execute_sql(query, show_internal, db)
    
    # Add to message history
    st.session_state.message_log.append({
        "internal": {"role": "user", "content": query},
        "display": {"role": "user", "content": f"```sql\n{query}\n```"}
    })
    st.session_state.message_log.append({
        "internal": {"role": "ai", "content": f"DuckDB:\n{result_text}"},
        "display": {"role": "ai", "content": None}
    })
    return error

def process_ai_response(response: str, show_internal: bool, db: Database, chat_engine: ChatEngine):
    """Process AI response, execute SQL, collect results"""
    parsed_response = chat_engine.parse_response(response)
    sql_errors = []
    sql_results = []
    display_text = []
    
    # Handle SQL execution
    for block in parsed_response.get("sql", []):
        if sql := block.get("query"):
            result_text, error = execute_sql(sql, show_internal, db)
            sql_results.append(result_text)
            if error:
                sql_errors.append(error)
    
    # Collect display text
    for item in parsed_response.get("display", []):
        display_text.append(item['text'])
    
    final_display = "\n\n".join(display_text)
    if sql_errors:
        final_display += "\n\n⚠️ SQL Errors:\n" + "\n".join(sql_errors)
    
    return final_display, sql_results

def update_message_history(ai_response: str, final_display: str, sql_results: list):
    """Add AI response and SQL results to message history"""
    # First add the AI's full response
    st.session_state.message_log.append({
        "internal": {"role": "ai", "content": ai_response},
        "display": {"role": "ai", "content": final_display}
    })
    
    # Then add each SQL result
    for result in sql_results:
        st.session_state.message_log.append({
            "internal": {"role": "ai", "content": f"DuckDB:\n{result}"},
            "display": {"role": "ai", "content": None}  # No display content for DuckDB messages
        })

def initialize_session_state():
    """Initialize the session state with first message"""
    if "message_log" not in st.session_state:
        with open('prompts/first.txt', 'r') as f:
            first_message = f.read()
        st.session_state.message_log = []
        parsed_first_message = parse_markup(first_message).get("display", [])
        rendered_first_message = "\n".join(item['text'] for item in parsed_first_message)
        st.session_state.message_log.append({
            "internal": {"role": "ai", "content": first_message},
            "display": {"role": "ai", "content": rendered_first_message}
        })

def setup_ui(chat_engine: ChatEngine):
    """Setup the UI components"""
    st.title("🐇 List Pet")
    st.caption("📋 An AI Data Assistant (instead of a spreadsheet!)")
    
    with st.sidebar:
        st.header("⚙️ Configuration")
        selected_model = st.selectbox(
            "Choose a model",
            ["gpt-4o-mini"],
            index=0
        )
        show_internal = st.checkbox("Show internal messages", value=False)
        show_prompt = st.checkbox("Show Current Prompt", value=False)
        
        if show_prompt:
            st.subheader("Current Prompt")
            prompt_chain = chat_engine.build_prompt_chain(st.session_state.message_log)
            messages = prompt_chain.format_messages()
            prompt_json = [{"type": msg.type, "content": msg.content} for msg in messages]
            st.json(prompt_json)
            
    return selected_model, show_internal, show_prompt

def handle_pending_query(show_internal: bool, chat_engine: ChatEngine, db: Database):
    """Process a pending AI query"""
    print("Processing pending query...")
    full_response = ""

    with st.spinner("🧠 Processing..."):
        prompt_chain = chat_engine.build_prompt_chain(st.session_state.message_log)
        
        if show_internal:
            with st.chat_message("internal"):
                internal_container = st.empty()
                internal_response = ""
                for chunk in chat_engine.generate_response_stream(prompt_chain):
                    full_response += chunk
                    internal_response += chunk
                    internal_container.markdown(internal_response)
        else:
            for chunk in chat_engine.generate_response_stream(prompt_chain):
                full_response += chunk

    final_display, sql_results = process_ai_response(full_response, show_internal, db, chat_engine)
    
    with st.chat_message("ai"):
        st.markdown(final_display)
    
    update_message_history(full_response, final_display, sql_results)
    
    del st.session_state.pending_query
    st.rerun()

# Main application flow
def main():
    initialize_session_state()
    
    # Start with default model
    default_model = "gpt-4o-mini"
    chat_engine = get_chat_engine(default_model)
    db = get_database()
    
    # Get UI settings
    selected_model, show_internal, show_prompt = setup_ui(chat_engine)
    
    # Recreate chat engine if model changed
    if selected_model != default_model:
        chat_engine = get_chat_engine(selected_model)
    
    # Display chat history
    for message in st.session_state.message_log:
        display_message(message, show_internal)
    
    # Handle new messages
    if user_query := st.chat_input("Type your question here..."):
        if is_sql_query(user_query):
            handle_sql_query(user_query, show_internal, db)
        else:
            st.session_state.pending_query = user_query
            st.session_state.message_log.append({
                "internal": {"role": "user", "content": user_query},
                "display": {"role": "user", "content": user_query}
            })
            st.rerun()
    
    # Process pending queries
    if "pending_query" in st.session_state:
        handle_pending_query(show_internal, chat_engine, db)

if __name__ == "__main__":
    main()
