import streamlit as st
import os
from chat import ChatEngine, get_chat_engine
from database import Database, get_database
from parse import parse_markup
import re
import pandas as pd
import json
from datetime import datetime
from plotting import get_plotter
import plotly.express as px

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
        # content = (content
        #           .replace("{{", "{{{{")
        #           .replace("}}", "}}}}")
        #           .replace("```", "\`\`\`"))
        
        if msg["role"] == USER_ROLE:
            example.append(content)
        elif msg["role"] == ASSISTANT_ROLE:
            example.append(f"{ASSISTANT_ROLE}:\n{content}")
    return "\n\n".join(example) + "\n"

def is_command(text: str) -> tuple[bool, str | None, str | None]:
    """Check if text is a system command and return (is_command, command_type, filename_stem)"""
    text = text.strip().upper()
    if text.startswith("DUMP "):
        parts = text[5:].strip().split()
        dump_type = parts[0]
        filename_stem = parts[1] if len(parts) > 1 else None
        
        if dump_type in ["JSON", "EXAMPLE", "TRAIN"]:
            return True, dump_type, filename_stem
        # Check for DUMP -N pattern
        if dump_type.startswith("-"):
            try:
                n = int(dump_type[1:])
                return True, dump_type, filename_stem
            except ValueError:
                pass
    return False, None, None

def handle_command(command_type: str, command_label: str | None) -> str:
    """Handle system commands and return the result text"""
    # Make a deep copy to avoid side effects
    messages = [msg.copy() for msg in st.session_state.messages]

    def dump_file_name(command_type: str, stem: str | None = None) -> str:
        dump_dir = "dumps"
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = (stem or "dump") + "_" + command_type + "_" + now
        extension = ".json" if command_type == "JSON" else ".txt"
        return dump_dir + "/" + stem + extension
    
    def write_dump_file(dump: str, command_type: str, stem: str | None = None):
        filename = dump_file_name(command_type, stem) 
        with open(filename, "w") as f:
            f.write(dump)
    
    if command_type == "JSON":
        # Create clean messages without modifying originals
        clean_messages = []
        for msg in messages:
            clean_msg = {k: v for k, v in msg.items() if k != "dataframe"}
            clean_messages.append(clean_msg)
        dump = json.dumps(clean_messages, indent=2)
        write_dump_file(dump, command_type, command_label)
        return f"{dump}"
    elif command_type == "EXAMPLE":
        dump = format_messages_example(messages)
        write_dump_file(dump, command_type, command_label)
        return f"{dump}"
    elif command_type == "TRAIN":
        return "```\nTraining data dump format (placeholder)\n```"
    elif command_type.startswith("-"):
        try:
            n = int(command_type[1:])
            if not n > 0:
                n = None
            dump = format_messages_example(messages, n)
            write_dump_file(dump, command_type, command_label)
            return f"{dump}"
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
            # For assistant messages, parse and display blocks
            parsed = parse_markup(message["content"])
            print("DEBUG - Display parsed message:", parsed)
            
            # Display text from display blocks
            display_text = "\n\n".join(item["text"] for item in parsed.get("display", []))
            st.markdown(display_text)
            
            # We don't need to recreate plots here anymore
            # Plots will be created in handle_ai_response and stored in the message log
            
        elif "figure" in message:
            # This is a plot message with a stored figure
            try:
                # Use the stored plot message ID if available, otherwise generate one
                plot_msg_id = message.get("plot_msg_id")
                if not plot_msg_id:
                    # Fallback to generating an ID if not stored (shouldn't happen with new code)
                    msg_idx = st.session_state.messages.index(message)
                    plot_idx = message.get("plot_index", 0)
                    plot_msg_id = f"stored_plot_{msg_idx}_{plot_idx}"
                
                # Display the plot with the consistent ID
                st.plotly_chart(message["figure"], use_container_width=True, key=plot_msg_id)
            except Exception as e:
                st.error(f"Error displaying plot: {str(e)}")
                print(f"DEBUG - Plot display error: {str(e)}")
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
    print("DEBUG - Parsed response:", parsed)
    
    last_df = None  # Keep track of the last dataframe for plots
    
    # Execute any SQL blocks
    had_error = False
    for block in parsed.get("sql", []):
        if query := block.get("query"):
            result, is_error, df = execute_sql(query, db)
            # Store SQL results
            sql_message = {"role": USER_ROLE, "content": f"{DATABASE_ACTOR}:\n{result}", "dataframe": df}
            st.session_state.messages.append(sql_message)
            had_error = had_error or is_error
            if df is not None:
                last_df = df
                print(f"DEBUG - SQL result dataframe: {df.shape}, columns: {df.columns.tolist()}")
    
    # Handle any plot blocks - this is the ONLY place where plots are created
    if last_df is not None and parsed.get("plot", []):
        print(f"DEBUG - Found {len(parsed.get('plot', []))} plot specifications to process")
        plotter = get_plotter()
        for i, plot_spec in enumerate(parsed.get("plot", [])):
            print(f"DEBUG - Processing plot {i+1}/{len(parsed.get('plot', []))}: {plot_spec}")
            try:
                # Create the plot
                fig, error = plotter.create_plot(plot_spec, last_df)
                
                if error:
                    # Handle plot creation error
                    print(f"DEBUG - Plot creation error: {error}")
                    
                    # Create a more user-friendly error message that includes the original plot spec
                    plot_type = plot_spec.get('type', 'unknown')
                    error_content = f"{DATABASE_ACTOR}:\n\n**Error creating {plot_type} plot:**\n```\n{error}\n```\n\nPlot specification:\n```json\n{json.dumps(plot_spec, indent=2)}\n```"
                    
                    # Add the error message to the conversation
                    plot_error = {"role": USER_ROLE, "content": error_content, "dataframe": last_df}
                    st.session_state.messages.append(plot_error)
                    
                    # Display the error in the UI
                    with st.chat_message(USER_ROLE):
                        st.markdown(error_content)
                elif fig:
                    # Generate a unique message ID for this plot
                    plot_msg_id = f"plot_{len(st.session_state.messages)}_{i}"
                    print(f"DEBUG - Plot created successfully with ID: {plot_msg_id}")
                    
                    # Store the figure object directly in the message
                    plot_message = {
                        "role": USER_ROLE, 
                        "content": f"{DATABASE_ACTOR}:\nPlot created successfully", 
                        "dataframe": last_df,
                        "figure": fig,
                        "plot_index": i,
                        "plot_msg_id": plot_msg_id  # Store a consistent ID for the plot
                    }
                    
                    # Add the plot message to the session state
                    st.session_state.messages.append(plot_message)
                    
                    # Display the plot with the unique ID
                    st.plotly_chart(fig, use_container_width=True, key=plot_msg_id)
                    print(f"DEBUG - Plot displayed with key: {plot_msg_id}")
                else:
                    print("DEBUG - No figure and no error returned from create_plot")
            except Exception as e:
                # Handle any unexpected errors
                error_msg = f"Error creating plot: {str(e)}"
                print(f"DEBUG - Plot error: {str(e)}")
                import traceback
                traceback_str = traceback.format_exc()
                print(f"DEBUG - Plot error traceback: {traceback_str}")
                
                # Create a more user-friendly error message
                plot_type = plot_spec.get('type', 'unknown')
                error_content = f"{DATABASE_ACTOR}:\n\n**Error creating {plot_type} plot:**\n```\n{error_msg}\n```\n\nPlot specification:\n```json\n{json.dumps(plot_spec, indent=2)}\n```"
                
                # Add the error message to the conversation
                plot_error = {"role": USER_ROLE, "content": error_content, "dataframe": last_df}
                st.session_state.messages.append(plot_error)
                
                # Display the error in the UI
                with st.chat_message(USER_ROLE):
                    st.markdown(error_content)
    elif parsed.get("plot", []):
        print("DEBUG - Plot specifications found but no dataframe available")
        
        # Create an error message for missing dataframe
        error_content = f"{DATABASE_ACTOR}:\n\n**Error creating plot:**\n```\nNo data available for plotting. Please run a SQL query first.\n```"
        
        # Add the error message to the conversation
        plot_error = {"role": USER_ROLE, "content": error_content}
        st.session_state.messages.append(plot_error)
        
        # Display the error in the UI
        with st.chat_message(USER_ROLE):
            st.markdown(error_content)
    elif last_df is not None:
        print("DEBUG - Dataframe available but no plot specifications found")
    
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
    if user_input := st.chat_input(
        "Type your question here...",
        key=f"chat_input_{len(st.session_state.messages)}"
    ):
        # Check if it's a command first
        is_cmd, cmd_type, cmd_label = is_command(user_input)
        if is_cmd:
            # All commands are diagnostic/utility - show output but don't add to state
            result = handle_command(cmd_type, cmd_label)
            # Show the command input and output without adding to state
            with st.chat_message(USER_ROLE):
                st.markdown(f"{USER_ACTOR}: {user_input}")
            with st.expander("Command Output (not saved to conversation)", expanded=True):
                # Use st.text() to show raw output for easy copying
                st.text(result)  # Remove outer backticks since st.text adds its own monospace formatting
            # Return early to prevent further processing
            return  # Prevent further processing to avoid triggering plots
        else:
            # For non-commands, add to message history and show
            with st.chat_message(USER_ROLE):
                st.markdown(f"{USER_ACTOR}: {user_input}")
            st.session_state.messages.append({"role": USER_ROLE, "content": f"{USER_ACTOR}: {user_input}"})
            
            # Then check if it's SQL
            if is_sql_query(user_input):
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
    
    # Add focus script at the end
    import streamlit.components.v1 as components
    components.html("""
        <script>
            // Function to focus the chat input
            function focusChatInput() {
                const doc = window.parent.document;  // break out of the Streamlit IFrame
                const inputs = doc.querySelectorAll('textarea');
                for (const input of inputs) {
                    if (input.placeholder === 'Type your question here...') {
                        input.focus();
                        break;
                    }
                }
            }
            
            // Call immediately and also after a short delay to ensure elements are loaded
            focusChatInput();
            setTimeout(focusChatInput, 100);
        </script>
    """, height=0, width=0)

if __name__ == "__main__":
    main()
