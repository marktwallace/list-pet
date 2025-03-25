from datetime import datetime
import os
import re

import duckdb
import streamlit as st
import pandas as pd

from langchain_core.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    AIMessagePromptTemplate,
    ChatPromptTemplate
)
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from .prompt_loader import get_prompts
from .database import Database
from .parsing import get_elements, SQL_REGEX
from .chart_renderer import render_chart

logfile = None

# Define roles
USER_ROLE = "user"
ASSISTANT_ROLE = "assistant"
SYSTEM_ROLE = "system"

avatars = {
    USER_ROLE: "assets/avatars/data_scientist_128px.png",
    ASSISTANT_ROLE: "assets/avatars/list_pet_128px.png",
    SYSTEM_ROLE: "assets/avatars/list_pet_128px.png"
}

def add_message(role, content, db):
    message = {"role": role, "content": content}
    st.session_state.db_messages.append(message)
    db.log_message(message)
    global logfile
    logfile.write(f"{role}:\n{content}\n\n")
    logfile.flush()

    if role == USER_ROLE:
        st.session_state.lc_messages.append(HumanMessagePromptTemplate.from_template(content))
    elif role == ASSISTANT_ROLE:
        st.session_state.lc_messages.append(AIMessagePromptTemplate.from_template(content))
    elif role == SYSTEM_ROLE:
        st.session_state.lc_messages.append(SystemMessagePromptTemplate.from_template(content))
            
def init_session_state(sess, db):
    sess.prompts = get_prompts()
    sess.lc_messages = []
    sess.lc_messages.append(SystemMessagePromptTemplate.from_template(sess.prompts["system_prompt"]))
    sess.db_messages = db.load_messages()
    if len(sess.db_messages) == 0:
        add_message(role=SYSTEM_ROLE, content=sess.prompts["welcome_message"], db=db)
    sess.pending_chart = False
    sess.pending_sql = False
    sess.pending_response = False
    sess.table_counters = {}
    sess.latest_dataframes = {}

def title_text(input):
    return input[:90] + "..." if len(input) > 60 else input

def handle_regenerate_button(button_key, sql, db, dataframe_key):
    """Handle regeneration button for dataframes and figures"""
    if st.button("Regenerate", key=button_key, type="primary", use_container_width=True):
        df, err = db.execute_query(sql)
        if err:
            print(f"ERROR - {err} for regeneration while rerunning SQL: {sql}")
            return False
        else:
            st.session_state[dataframe_key] = df
            st.rerun()
    return False

def display_dataframe_item(item, idx, sess, db):
    """Display a dataframe element with its expander and regeneration button if needed"""
    content = item["content"]
    attributes = item["attributes"]
    if not attributes.get("name"):
        st.error("Dataframe must have a name")
        return
    
    # Get the semantic identifier and display name
    semantic_id = attributes.get("name")
    display_name = attributes.get("display_name", attributes.get("table", semantic_id))
    
    with st.expander(title_text(display_name), expanded=True):
        key = "dataframe_" + semantic_id
        if key in sess:
            df = sess[key]
            st.dataframe(df, use_container_width=True, hide_index=True)
            return
        
        # Dataframe not found, try to regenerate
        print(f"DEBUG - Dataframe not found in session state with key: {key}")
        msg_idx = attributes.get("msg_idx")
        tag_idx = attributes.get("tag_idx")
        
        if msg_idx is None or tag_idx is None:
            st.error("Missing msg_idx or tag_idx for dataframe")
            return
            
        try:
            msg_idx, tag_idx = int(msg_idx), int(tag_idx)
            msg_ref_content = sess.db_messages[msg_idx]["content"]
            msg_ref = get_elements(msg_ref_content)
            arr = msg_ref.get("sql", [])
            
            if arr and tag_idx < len(arr):
                sql = arr[tag_idx]["content"]
                button_key = f"df_btn_{idx}_{msg_idx}_{tag_idx}"
                handle_regenerate_button(button_key, sql, db, key)
            else:
                st.error("Missing sql for dataframe regeneration")
        except (ValueError, IndexError) as e:
            st.error(f"Error processing dataframe indices: {str(e)}")

def display_figure_item(item, idx, sess, db):
    """Display a figure element with its expander and regeneration button if needed"""
    content = item["content"]
    attributes = item["attributes"]
    if not attributes.get("dataframe"):
        st.error("Figure must have a dataframe")
        return
    
    # Get the semantic identifier and prepare keys
    semantic_id = attributes.get("dataframe")
    dataframe_key = "dataframe_" + semantic_id
    
    # Get the chart configuration from session state
    chart_config_key = f"chart_config_{semantic_id}"
    chart_content = sess.get(chart_config_key, "")
    
    # Create a unique figure key using the chart content
    content_hash = hash(chart_content) % 100000  # Keep it to 5 digits
    figure_key = f"figure_{idx}_{semantic_id}_{content_hash}"
    
    # Use the figure content as the title (it should contain only the title text)
    title = content.strip()
    
    # Fallback if title is empty
    if not title:
        display_name = semantic_id.split("_")[0] if "_" in semantic_id else semantic_id
        title = f"Chart for {display_name}"
    
    with st.expander(title_text(title), expanded=True):
        # If dataframe exists, render chart or retrieve from cache
        if dataframe_key in sess:
            # Check if figure is already cached in session state
            if figure_key in sess:
                fig = sess[figure_key]
                st.plotly_chart(fig, use_container_width=True, key=figure_key)
            else:
                df = sess[dataframe_key]
                # Use the stored chart configuration instead of the figure content
                fig, err = render_chart(df, chart_content)
                
                if err:
                    st.error(f"Error rendering chart: {err}")
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    # Cache the figure in session state
                    sess[figure_key] = fig
                    print(f"DEBUG - Caching new figure with key: {figure_key}")
                    st.plotly_chart(fig, use_container_width=True, key=figure_key)
            return
        
        # Dataframe doesn't exist, show regeneration button
        st.info(f"The dataframe '{semantic_id}' is not available. Click the button below to regenerate it.")
        
        msg_idx = attributes.get("msg_idx")
        tag_idx = attributes.get("tag_idx")
        
        if msg_idx is None or tag_idx is None:
            st.error("Missing msg_idx or tag_idx for figure dataframe")
            return
            
        try:
            msg_idx, tag_idx = int(msg_idx), int(tag_idx)
            msg_ref_content = sess.db_messages[msg_idx]["content"]
            msg_ref = get_elements(msg_ref_content)
            arr = msg_ref.get("sql", [])
            
            if arr and tag_idx < len(arr):
                sql = arr[tag_idx]["content"]
                button_key = f"fig_btn_{idx}_{msg_idx}_{tag_idx}"
                if handle_regenerate_button(button_key, sql, db, dataframe_key):
                    # Clear the cached figure when regenerating the dataframe
                    if figure_key in sess:
                        del sess[figure_key]
            else:
                st.error("Missing SQL for figure dataframe regeneration")
        except (ValueError, IndexError) as e:
            st.error(f"Error processing figure indices: {str(e)}")

def process_sql_query(sql_tuple, db):
    """Process an SQL query and store results as a dataframe"""
    sess = st.session_state
    tag_idx, sql_item = sql_tuple
    sql = sql_item["content"]
    msg_idx = len(sess.db_messages) - 1

    # Execute query and handle errors
    df, err = db.execute_query(sql)
    if err:
        add_message(role=USER_ROLE, content=f"<error>\n{err}\n</error>\n", db=db)
        return True
    
    if df is None:
        return True
    
    # Extract table name from SQL
    table_match = re.search(r"FROM\s+(\w+(?:\.\w+)?)", sql, re.IGNORECASE)
    table_name = table_match.group(1) if table_match else "unknown"
    print(f"DEBUG - Using table name: {table_name} for dataframe")
    
    # Create semantic ID
    if table_name not in sess.table_counters:
        sess.table_counters[table_name] = 1
    else:
        sess.table_counters[table_name] += 1
    
    semantic_id = f"{table_name}_{sess.table_counters[table_name]}"
    sess.latest_dataframes[table_name] = semantic_id
    
    # Store dataframe in session state
    dataframe_key = f"dataframe_{semantic_id}"
    sess[dataframe_key] = df
    
    # Store provenance information
    sess[f"provenance_{semantic_id}"] = {
        "msg_idx": msg_idx, "tag_idx": tag_idx, 
        "sql": sql, "timestamp": datetime.now().isoformat()
    }
    
    # Format preview for display
    preview_rows = min(5, len(df)) if len(df) > 20 else len(df)
    tsv_lines = ["\t".join(df.columns)]
    tsv_lines.extend("\t".join(str(val) for val in row) for _, row in df.iloc[:preview_rows].iterrows())
    if preview_rows < len(df):
        tsv_lines.append("...")
    
    # Create and add dataframe message
    content = f'<dataframe name="{semantic_id}" table="{table_name}" msg_idx="{msg_idx}" tag_idx="{tag_idx}" >\n'
    content += "\n".join(tsv_lines) + "\n</dataframe>\n"
    
    print(f"DEBUG - Adding dataframe with semantic ID: {semantic_id}")
    add_message(role=USER_ROLE, content=content, db=db)
    return True

def process_chart_request(chart_tuple):
    """Process a chart request and create a figure element"""
    sess = st.session_state
    chart_idx, chart_item = chart_tuple
    chart_content = chart_item["content"]
    chart_attrs = chart_item["attributes"]
    
    # Validate chart request
    df_reference = chart_attrs.get("dataframe")
    if not df_reference:
        st.error("Chart missing dataframe reference")
        return True
    
    # Resolve dataframe reference (table name or direct semantic ID)
    semantic_id = sess.latest_dataframes.get(df_reference, df_reference)
    provenance_key = f"provenance_{semantic_id}"
    
    # Validate dataframe exists
    if provenance_key not in sess:
        st.error(f"Could not find dataframe: {semantic_id}")
        return True
    
    # Get provenance
    provenance = sess[provenance_key]
    msg_idx, tag_idx = provenance.get("msg_idx"), provenance.get("tag_idx")
    
    # Extract title from chart content if available
    title = None
    title_match = re.search(r'title:\s*(.*?)$', chart_content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        # Fallback title
        title = f"Chart for {semantic_id.split('_')[0]}"
    
    # Store chart content in session state for later use
    chart_config_key = f"chart_config_{semantic_id}"
    sess[chart_config_key] = chart_content
    
    # Create figure content with only the title in the content (not as an attribute)
    figure_content = (
        f'<figure dataframe="{semantic_id}" msg_idx="{msg_idx}" tag_idx="{tag_idx}">\n'
        f'{title}\n'
        f'</figure>'
    )
    
    print(f"DEBUG - Creating figure for dataframe: {semantic_id}")
    add_message(role=ASSISTANT_ROLE, content=figure_content, db=Database())
    return True

def display_message(idx, message, sess, db):
    """Display a chat message with its components"""
    with st.chat_message(message["role"], avatar=avatars.get(message["role"])):
        msg = get_elements(message["content"])
        
        if "markdown" in msg:
            st.markdown(msg["markdown"])
        
        if "sql" in msg:
            for item in msg["sql"]:
                with st.expander(title_text(item["content"]), expanded=False):
                    st.code(item["content"])

        if "dataframe" in msg:
            for item in msg["dataframe"]:
                display_dataframe_item(item, idx, sess, db)

        if "figure" in msg:
            for item in msg["figure"]:
                display_figure_item(item, idx, sess, db)

        if "error" in msg:
            for item in msg["error"]:
                with st.expander(title_text(item["content"]), expanded=False):
                    st.code(item["content"])

def generate_llm_response():
    """Generate a response from the LLM and process it"""
    sess = st.session_state
    sess.pending_response = False
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
    prompt_template = ChatPromptTemplate.from_messages(sess.lc_messages)
    processing_pipeline = prompt_template | llm | StrOutputParser()
    response = "".join(processing_pipeline.stream({}))
    add_message(role=ASSISTANT_ROLE, content=response, db=Database())
    msg = get_elements(response)
    sess.pending_sql = list(enumerate(msg.get("sql", [])))
    print(f"DEBUG - pending_sql: {sess.pending_sql}")
    sess.pending_chart = list(enumerate(msg.get("chart", [])))       
    return True

def main():
    global logfile
    if logfile is None:
        log_dir = f"logs/{datetime.now().strftime('%m-%d')}"
        os.makedirs(log_dir, exist_ok=True)
        logfile = open(f"{log_dir}/{datetime.now().strftime('%H-%M')}.log", "w")
    
    sess = st.session_state
    if "conn" not in sess: # first time the app is run
        sess.conn = duckdb.connect('db/list_pet.db')
        db = Database()
        db.initialize_pet_meta_schema()
        init_session_state(sess, db)
    else:
        db = Database()
    
    st.set_page_config(page_title="List Pet", page_icon="🐾", layout="wide")
    st.title("🐾 List Pet")
    st.caption("Your friendly SQL assistant")

    # Display chat messages
    for idx, message in enumerate(sess.db_messages):
        display_message(idx, message, sess, db)

    # Process pending items
    if sess.pending_sql and sess.pending_sql[0]:
        sql_tuple = sess.pending_sql.pop(0)
        if process_sql_query(sql_tuple, db):
            st.rerun()

    if sess.pending_chart and sess.pending_chart[0]:
        chart_tuple = sess.pending_chart.pop(0)
        if process_chart_request(chart_tuple):
            st.rerun()

    if sess.pending_response:
        if generate_llm_response():
            st.rerun()
        
    # Process user input    
    if input := st.chat_input("Type your message..."):
        # Process SQL syntax
        if re.match(SQL_REGEX, input.strip(), re.IGNORECASE):
            input = "<sql>\n" + input + "\n</sql>\n"
        
        add_message(role=USER_ROLE, content=input, db=db)
        sess.pending_response = True
        
        # Check for SQL in input
        msg = get_elements(input)
        if msg.get("sql"):
            sess.pending_sql = list(enumerate(msg.get("sql", [])))
            
        st.rerun()
