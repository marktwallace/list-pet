import streamlit as st
import os
from chat import ChatEngine, get_chat_engine
from database import Database, get_database
from parse import parse_markup
import re
import pandas as pd
import json

# Constants
ASSISTANT_ROLE = "Assistant"
USER_ROLE = "User"
USER_ACTOR = "User"
DATABASE_ACTOR = "DuckDB"

def format_sql_result(query: str, df: pd.DataFrame | None, error: str | None) -> tuple[str, pd.DataFrame | None]:
    """Format SQL results in a consistent way, returning both display text and dataframe"""
    output = []
    output.append(f"SQL Query:")
    output.append(f"```sql\n{query}\n```")
    
    if error:
        output.append("Error:")
        output.append(f"```\n{error}\n```")
        return "\n".join(output), None
    elif df is not None:
        # Format for AI prompt using TSV
        tsv_output = []
        tsv_output.append("\t".join(df.columns))  # Headers
        for _, row in df.iterrows():
            tsv_output.append("\t".join(str(val) for val in row))
        
        output.append("Result:")
        output.append("```tsv\n" + "\n".join(tsv_output) + "\n```")
        return "\n".join(output), df
    return "\n".join(output), None

def is_sql_query(text: str) -> bool:
    """Check if text is SQL (either explicit <sql> tag or common SQL patterns)"""
    text = text.strip()
    return text.startswith("<sql>") or bool(re.match(
        r"^\s*(?:"
        r"SELECT\s+(?:\w+|\*)|"
        r"CREATE\s+(?:TABLE|DATABASE|VIEW|INDEX)|"
        r"DROP\s+(?:TABLE|DATABASE|VIEW|INDEX)|"
        r"ALTER\s+(?:TABLE|DATABASE|VIEW)|"
        r"INSERT\s+INTO|"
        r"DELETE\s+FROM|"
        r"UPDATE\s+\w+|"
        r"SHOW\s+(?:TABLES|DATABASES|COLUMNS)|"
        r"DESCRIBE\s+\w+"
        r")\s*.*",
        text, re.IGNORECASE
    ))

def is_command(text: str) -> tuple[bool, str | None]:
    """Check if text is a system command and return (is_command, command_type)"""
    text = text.strip().upper()
    if text.startswith("DUMP "):
        dump_type = text[5:].strip()
        if dump_type in ["JSON", "EXAMPLE", "TRAIN"]:
            return True, dump_type
    return False, None

def handle_command(command_type: str) -> str:
    """Handle system commands and return the result text"""
    # Make a deep copy to avoid side effects
    messages = [msg.copy() for msg in st.session_state.messages]
    
    if command_type == "JSON":
        # Create clean messages without modifying originals
        clean_messages = []
        for msg in messages:
            clean_msg = {k: v for k, v in msg.items() if k != "dataframe"}
            clean_messages.append(clean_msg)
        return f"```json\n{json.dumps(clean_messages, indent=2)}\n```"
    elif command_type == "EXAMPLE":
        # Convert to example format (User/Assistant alternating format)
        example = []
        for msg in messages:
            if msg["role"] == USER_ROLE:
                content = msg["content"]
                if content.startswith(f"{USER_ACTOR}: "):
                    content = content[len(f"{USER_ACTOR}: "):]
                example.append(f"Human: {content}")
            elif msg["role"] == ASSISTANT_ROLE:
                example.append(f"Assistant: {msg['content']}")
        return "```\n" + "\n\n".join(example) + "\n```"
    elif command_type == "TRAIN":
        return "```\nTraining data dump format (placeholder)\n```"
    
    return "Invalid dump type"

def execute_sql(query: str, db: Database) -> tuple[str, bool, pd.DataFrame | None]:
    """Execute SQL and return (formatted_result, had_error, dataframe)"""
    df, error = db.execute_query(query)
    result, df = format_sql_result(query, df, error)
    return result, bool(error), df

def display_message(message: dict):
    """Display a message in user-friendly format"""
    with st.chat_message(message["role"]):
        if message["role"] == ASSISTANT_ROLE:
            # For assistant messages, parse and display only display blocks
            parsed = parse_markup(message["content"])
            display_text = "\n\n".join(item["text"] for item in parsed.get("display", []))
            st.markdown(display_text)
        else:
            # For user/database messages, split into parts
            content = message["content"]
            if message["content"].startswith(f"{DATABASE_ACTOR}:"):
                # Extract query and result sections
                parts = content.split("```")
                st.markdown(f"```{parts[1]}```")  # Show SQL query
                
                if len(parts) > 3:  # If we have results
                    if "Error:" in content:
                        st.markdown(f"```{parts[3]}```")  # Show error
                    else:
                        # Get the dataframe from the message's metadata
                        df = message.get("dataframe")
                        if df is not None:
                            st.dataframe(
                                df,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    col: st.column_config.Column(
                                        width="auto"
                                    ) for col in df.columns
                                }
                            )
            else:
                st.markdown(content)

def handle_ai_response(response: str, chat_engine: ChatEngine, db: Database, retry_count: int = 0) -> None:
    """Process AI response, executing any SQL and handling errors"""
    # Store complete AI response with all markup
    st.session_state.messages.append({"role": ASSISTANT_ROLE, "content": response})
    
    parsed = parse_markup(response)
    
    # Execute any SQL blocks
    had_error = False
    for block in parsed.get("sql", []):
        if query := block.get("query"):
            result, is_error, df = execute_sql(query, db)
            # Store SQL results
            sql_message = {"role": USER_ROLE, "content": f"{DATABASE_ACTOR}:\n{result}", "dataframe": df}
            st.session_state.messages.append(sql_message)
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
    
    if "needs_ai_response" not in st.session_state:
        st.session_state.needs_ai_response = False
    
    # Setup chat engine and database
    chat_engine = get_chat_engine("gpt-4o-mini")
    db = get_database()
    
    # Display conversation history with user-friendly formatting
    for message in st.session_state.messages:
        display_message(message)
    
    # Handle new input
    if user_input := st.chat_input("Type your question here..."):
        # Always show user input immediately
        st.session_state.messages.append({"role": USER_ROLE, "content": f"{USER_ACTOR}: {user_input}"})
        
        # Check if it's a command first
        is_cmd, cmd_type = is_command(user_input)
        if is_cmd:
            result = handle_command(cmd_type)
            cmd_message = {"role": USER_ROLE, "content": f"System:\n{result}"}
            st.session_state.messages.append(cmd_message)
            st.rerun()
        # Then check if it's SQL
        elif is_sql_query(user_input):
            result, had_error, df = execute_sql(user_input, db)
            sql_message = {"role": USER_ROLE, "content": f"{DATABASE_ACTOR}:\n{result}", "dataframe": df}
            st.session_state.messages.append(sql_message)
            st.session_state.needs_ai_response = True
            st.rerun()
        else:
            # Regular message, needs AI response
            st.session_state.needs_ai_response = True
            st.rerun()
    
    # Handle AI response if needed
    if st.session_state.needs_ai_response:
        # Show thinking state
        with st.chat_message(ASSISTANT_ROLE):
            with st.spinner("Thinking..."):
                response = chat_engine.generate_response(st.session_state.messages)
                handle_ai_response(response, chat_engine, db)
                st.session_state.needs_ai_response = False
                st.rerun()
    
    # Scroll to bottom using JavaScript
    st.markdown("""
        <script>
            window.scrollTo(0, document.body.scrollHeight);
        </script>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
