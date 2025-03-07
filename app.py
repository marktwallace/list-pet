import streamlit as st
import os
import re
import json
import pandas as pd
from datetime import datetime
import plotly.express as px

from chat import ChatEngine, get_chat_engine
from database import Database, get_database
from parse import parse_markup
from plotting import get_plotter

# Import command-related utilities and constants
from commands import is_command, handle_command
from constants import ASSISTANT_ROLE, USER_ROLE, USER_ACTOR, DATABASE_ACTOR

def format_sql_result(query: str, df: pd.DataFrame | None, error: str | None) -> tuple[str, pd.DataFrame | None]:
    """Format SQL results in a consistent way, returning both display text and dataframe."""
    output = []
    output.append(f"```sql\n{query}\n```")
    
    if error:
        output.append("Error:")
        output.append(f"```\n{error}\n```")
        return "\n".join(output), None
    elif df is not None:
        tsv_output = []
        tsv_output.append("\t".join(df.columns))
        for _, row in df.iterrows():
            tsv_output.append("\t".join(str(val) for val in row))
        
        output.append("Result:")
        output.append("```tsv\n" + "\n".join(tsv_output) + "\n```")
        return "\n".join(output), df
    return "\n".join(output), None

def is_sql_query(text: str) -> bool:
    """Check if text is SQL (either explicit <sql> tag or common SQL patterns)."""
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

def execute_sql(query: str, db: Database) -> tuple[str, bool, pd.DataFrame | None]:
    """Execute SQL and return (formatted_result, had_error, dataframe)."""
    df, error = db.execute_query(query)
    result, df = format_sql_result(query, df, error)
    return result, bool(error), df

def format_sql_label(sql: str, max_length: int = 45) -> str:
    """Format SQL query into a concise label for the expander."""
    sql = sql.strip().replace('sql\n', '').strip()
    effective_length = max_length - 8
    first_line = sql.split('\n')[0].strip()
    if len(first_line) > effective_length or not first_line:
        words = sql.split()
        label = ' '.join(words[:4])
        if len(label) > effective_length:
            label = label[:effective_length]
    else:
        label = first_line[:effective_length]
    return f"SQL: {label}..."

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

def main():
    st.title("🐇 List Pet")
    st.caption("📋 An AI Data Assistant")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
        with open('prompts/first.txt', 'r') as f:
            first_message = f.read()
        st.session_state.messages.append({"role": ASSISTANT_ROLE, "content": first_message})
    
    if "needs_ai_response" not in st.session_state:
        st.session_state.needs_ai_response = False
    
    chat_engine = get_chat_engine("gpt-4o-mini")
    db = get_database()
    
    for message in st.session_state.messages:
        display_message(message)
    
    if user_input := st.chat_input("Type your question here...", key=f"chat_input_{len(st.session_state.messages)}"):
        is_cmd, cmd_type, cmd_label = is_command(user_input)
        if is_cmd:
            result = handle_command(cmd_type, cmd_label)
            with st.chat_message(USER_ROLE):
                st.markdown(f"{USER_ACTOR}: {user_input}")
            with st.expander("Command Output (not saved to conversation)", expanded=True):
                st.text(result)
            return
        else:
            with st.chat_message(USER_ROLE):
                st.markdown(f"{USER_ACTOR}: {user_input}")
            st.session_state.messages.append({"role": USER_ROLE, "content": f"{USER_ACTOR}: {user_input}"})
            if is_sql_query(user_input):
                result, had_error, df = execute_sql(user_input, db)
                sql_message = {"role": USER_ROLE, "content": f"{DATABASE_ACTOR}:\n{result}", "dataframe": df}
                st.session_state.messages.append(sql_message)
                st.session_state.needs_ai_response = True
                st.rerun()
            else:
                st.session_state.needs_ai_response = True
                st.rerun()
    
    if st.session_state.needs_ai_response:
        with st.chat_message(ASSISTANT_ROLE):
            with st.spinner("Thinking..."):
                response = chat_engine.generate_response(st.session_state.messages)
                handle_ai_response(response, chat_engine, db)
                st.session_state.needs_ai_response = False
                st.rerun()
    
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

if __name__ == "__main__":
    main()
