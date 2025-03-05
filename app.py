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

def format_messages_example(messages: list, limit: int | None = None) -> str:
    """Format messages in example format, optionally limiting to last N messages"""
    # If limit is specified, take only the last N messages
    if limit is not None:
        messages = messages[-limit:]
    
    # Convert to example format (User/Assistant alternating format)
    example = []
    for msg in messages:
        content = msg["content"]
        # Escape template variables and code blocks
        content = (content
                  .replace("{{", "{{{{")
                  .replace("}}", "}}}}")
                  .replace("```", "\\`\\`\\`"))
        
        if msg["role"] == USER_ROLE:
            example.append(content)
        elif msg["role"] == ASSISTANT_ROLE:
            example.append(f"{ASSISTANT_ROLE}: {content}")
    return "```\n" + "\n\n".join(example) + "\n```"

def is_command(text: str) -> tuple[bool, str | None]:
    """Check if text is a system command and return (is_command, command_type)"""
    text = text.strip().upper()
    if text.startswith("DUMP "):
        dump_type = text[5:].strip()
        if dump_type in ["JSON", "EXAMPLE", "TRAIN"]:
            return True, dump_type
        # Check for DUMP -N pattern
        if dump_type.startswith("-"):
            try:
                n = int(dump_type[1:])
                if n > 0:
                    return True, dump_type
            except ValueError:
                pass
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
        return format_messages_example(messages)
    elif command_type == "TRAIN":
        return "```\nTraining data dump format (placeholder)\n```"
    elif command_type.startswith("-"):
        try:
            n = int(command_type[1:])
            if n > 0:
                return format_messages_example(messages, n)
        except ValueError:
            pass
    
    return "Invalid dump type"

def execute_sql(query: str, db: Database) -> tuple[str, bool, pd.DataFrame | None]:
    """Execute SQL and return (formatted_result, had_error, dataframe)"""
    df, error = db.execute_query(query)
    result, df = format_sql_result(query, df, error)
    return result, bool(error), df

def format_sql_label(sql: str, max_length: int = 45) -> str:
    """Format SQL query into a concise label for the expander.
    Takes the first line or first few words of the SQL query."""
    # Remove any leading/trailing whitespace and 'sql' language marker
    sql = sql.strip().replace('sql\n', '').strip()
    
    # Account for "SQL: " prefix (5 chars) and "..." suffix (3 chars)
    effective_length = max_length - 8
    
    # Try to get first line
    first_line = sql.split('\n')[0].strip()
    
    # If it's too long or empty, take first few words
    if len(first_line) > effective_length or not first_line:
        words = sql.split()
        label = ' '.join(words[:4])
        if len(label) > effective_length:
            label = label[:effective_length]
    else:
        label = first_line[:effective_length]
    
    return f"SQL: {label}..."

def display_message(message: dict):
    """Display a message in user-friendly format"""
    with st.chat_message(message["role"]):
        if message["role"] == ASSISTANT_ROLE:
            # For assistant messages, parse and display only display blocks
            parsed = parse_markup(message["content"])
            display_text = "\n\n".join(item["text"] for item in parsed.get("display", []))
            st.markdown(display_text)
        else:
            # For user/database messages
            content = message["content"]
            if content.startswith(f"{DATABASE_ACTOR}:"):
                # Find SQL query and result sections using regex to be more robust
                import re
                
                # Extract SQL query
                sql_match = re.search(r"```(?:sql)?\s*\n?(.*?)\n?```", content, re.DOTALL)
                if sql_match:
                    sql_query = sql_match.group(1).strip()
                    # Show SQL query in an expander
                    with st.expander(format_sql_label(sql_query)):
                        st.markdown(f"```sql\n{sql_query}\n```")
                
                # Extract results or error
                if "Error:" in content:
                    error_match = re.search(r"Error:.*?```(.*?)```", content, re.DOTALL)
                    if error_match:
                        st.markdown(f"```\n{error_match.group(1).strip()}\n```")
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
    
    # Handle new input - use key parameter to control scrolling
    if user_input := st.chat_input("Type your question here...", key=f"chat_input_{len(st.session_state.messages)}"):
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

if __name__ == "__main__":
    main()
