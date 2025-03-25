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
            
def init_session_state(sess,db):
    sess.prompts = get_prompts()
    sess.lc_messages = []
    sess.lc_messages.append(SystemMessagePromptTemplate.from_template(sess.prompts["system_prompt"]))
    sess.db_messages = db.load_messages()
    if len(sess.db_messages) == 0:
        add_message(role=SYSTEM_ROLE, content=sess.prompts["welcome_message"], db=db)
    sess.pending_chart = False
    sess.pending_sql = False
    sess.pending_response = False
    # Initialize table counters and latest dataframes tracking
    if "table_counters" not in sess:
        sess.table_counters = {}
    if "latest_dataframes" not in sess:
        sess.latest_dataframes = {}

def title_text(input):
    return input[:90] + "..." if len(input) > 60 else input

def main():
    # Create a new log file in the logs directory, with a suddirectory (MM-dd) for each day,
    # named with the current hour and minute
    global logfile
    if logfile is None:
        # Create logs directory and subdirectory if they don't exist
        log_dir = f"logs/{datetime.now().strftime('%m-%d')}"
        os.makedirs(log_dir, exist_ok=True)
        logfile = open(f"{log_dir}/{datetime.now().strftime('%H-%M')}.log", "w")
    
    sess = st.session_state
    if "conn" not in sess: # first time the app is run
        sess.conn = duckdb.connect('db/list_pet.db')
        db = Database()
        db.initialize_pet_meta_schema()
        init_session_state(sess,db)
    else:
        db = Database()
    
    st.set_page_config(page_title="List Pet", page_icon="🐾", layout="wide")
    st.title("🐾 List Pet")
    st.caption("Your friendly SQL assistant")

    # Display chat messages
    for idx, message in enumerate(sess.db_messages):
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
                    content = item["content"]
                    attributes = item["attributes"]
                    if not attributes.get("name"):
                        st.error("Dataframe must have a name")
                        continue
                    
                    # Get the semantic identifier from the name attribute
                    semantic_id = attributes.get("name")
                    
                    # Use table name for display if available, otherwise use semantic ID
                    display_name = attributes.get("table", semantic_id)
                    if attributes.get("display_name"):
                        display_name = attributes.get("display_name")
                    
                    with st.expander(title_text(display_name), expanded=True):
                        key = "dataframe_" + semantic_id
                        if key in sess:
                            df = sess[key]
                            st.dataframe(df, use_container_width=True, hide_index=True)
                        else:
                            print(f"DEBUG - Dataframe not found in session state with key: {key}")
                            msg_idx = attributes.get("msg_idx")
                            tag_idx = attributes.get("tag_idx")
                            if msg_idx is not None and tag_idx is not None:
                                try:
                                    msg_idx = int(msg_idx)
                                    tag_idx = int(tag_idx)
                                    msg_ref_content = sess.db_messages[msg_idx]["content"]
                                    msg_ref = get_elements(msg_ref_content)
                                    arr = msg_ref.get("sql", [])
                                    if arr and tag_idx < len(arr):
                                        sql = arr[tag_idx]["content"]
                                        # Store SQL for later use if button is clicked
                                        button_key = f"df_btn_{idx}_{msg_idx}_{tag_idx}"
                                        if st.button(
                                            "Regenerate Dataframe",
                                            key=button_key,
                                            type="primary",
                                            use_container_width=True,
                                        ):
                                            df, err = db.execute_query(sql)
                                            if err:
                                                print(f"ERROR - {err} for dataframe regeneration while rerunning SQL: {sql}")
                                            else:
                                                sess[key] = df
                                                st.rerun()
                                    else:
                                        st.error("Missing sql for dataframe regeneration")
                                except (ValueError, IndexError) as e:
                                    st.error(f"Error processing dataframe indices: {str(e)}")
                            else:
                                st.error("Missing msg_idx or tag_idx for dataframe")

            if "figure" in msg:
                for item in msg["figure"]:
                    content = item["content"]
                    attributes = item["attributes"]
                    if not attributes.get("dataframe"):
                        st.error("Figure must have a dataframe")
                        continue
                    
                    # Get the semantic identifier from the dataframe attribute
                    semantic_id = attributes.get("dataframe")
                    dataframe_key = "dataframe_" + semantic_id
                    figure_key = f"figure_{idx}_{semantic_id}"
                    
                    # Extract table name from semantic ID for display purposes
                    if "_" in semantic_id:
                        display_name = semantic_id.split("_")[0]
                    else:
                        display_name = semantic_id
                    
                    title = attributes.get("title", f"Chart for {display_name}")
                    
                    with st.expander(title_text(title), expanded=True):
                        # Check if the referenced dataframe exists in session state
                        if dataframe_key in sess:
                            df = sess[dataframe_key]
                            
                            # Render the chart using our new chart_renderer
                            fig, err = render_chart(df, content)
                            
                            if err:
                                st.error(f"Error rendering chart: {err}")
                                # Fall back to displaying the dataframe
                                st.dataframe(df, use_container_width=True, hide_index=True)
                            else:
                                # Display the plotly figure
                                st.plotly_chart(fig, use_container_width=True)
                        else:
                            # Dataframe doesn't exist, we need a regeneration button
                            st.info(f"The dataframe '{semantic_id}' is not available. Click the button below to regenerate it.")
                            
                            msg_idx = attributes.get("msg_idx")
                            tag_idx = attributes.get("tag_idx")
                            
                            if msg_idx is not None and tag_idx is not None:
                                try:
                                    msg_idx = int(msg_idx)
                                    tag_idx = int(tag_idx)
                                    msg_ref_content = sess.db_messages[msg_idx]["content"]
                                    msg_ref = get_elements(msg_ref_content)
                                    arr = msg_ref.get("sql", [])
                                    
                                    if arr and tag_idx < len(arr):
                                        sql = arr[tag_idx]["content"]
                                        # Create a button for regenerating the dataframe
                                        button_key = f"fig_btn_{idx}_{msg_idx}_{tag_idx}"
                                        if st.button(
                                            "Regenerate Figure Data",
                                            key=button_key,
                                            type="primary",
                                            use_container_width=True,
                                        ):
                                            df, err = db.execute_query(sql)
                                            if err:
                                                st.error(f"Error: {err}")
                                                print(f"ERROR - {err} for figure dataframe regeneration while rerunning SQL: {sql}")
                                            else:
                                                # Store the dataframe in session state with semantic ID
                                                sess[dataframe_key] = df
                                                st.rerun()
                                    else:
                                        st.error("Missing SQL for figure dataframe regeneration")
                                except (ValueError, IndexError) as e:
                                    st.error(f"Error processing figure indices: {str(e)}")
                            else:
                                st.error("Missing msg_idx or tag_idx for figure dataframe")

            if "error" in msg:
                for item in msg["error"]:
                    with st.expander(title_text(item["content"]), expanded=False):
                        st.code(item["content"])

    if sess.pending_sql:
        # pop one sql message from the list, process it, then rerun()
        sql_tuple = sess.pending_sql.pop(0)
        print(f"DEBUG - sql_tuple: {sql_tuple}")
        tag_idx = sql_tuple[0]
        msg_idx = len(sess.db_messages) - 1
        sql = sql_tuple[1]["content"]

        df,err = db.execute_query(sql)
        if df is not None:
            print(f"DEBUG - Query returned dataframe with {len(df)} rows and {len(df.columns)} columns")
            tsv_output = []
            tsv_output.append("\t".join(df.columns))
            for idx, (_, row) in enumerate(df.iterrows()):
                if idx >= 5 and len(df) > 20:
                    tsv_output.append("...")
                    break
                tsv_output.append("\t".join(str(val) for val in row))
            # find the table name in the sql
            table_name = re.search(r"FROM\s+(\w+(?:\.\w+)?)", sql, re.IGNORECASE)
            if table_name:
                table_name = table_name.group(1)
                print(f"DEBUG - Detected table name for dataframe: {table_name}")
            else:
                table_name = "unknown"
                print(f"DEBUG - No table name detected for dataframe, using default: {table_name}")
            
            # Create a semantic identifier for the dataframe
            # Initialize or increment the counter for this table
            if table_name not in sess.table_counters:
                sess.table_counters[table_name] = 1
            else:
                sess.table_counters[table_name] += 1
            
            # Create the semantic identifier
            semantic_id = f"{table_name}_{sess.table_counters[table_name]}"
            
            # Update the latest dataframe reference for this table
            sess.latest_dataframes[table_name] = semantic_id
            
            # Store dataframe in session state with semantic ID
            dataframe_key = f"dataframe_{semantic_id}"
            sess[dataframe_key] = df
            print(f"DEBUG - Storing dataframe with semantic ID: {semantic_id}, key: {dataframe_key}")
            
            # Store provenance information
            provenance_key = f"provenance_{semantic_id}"
            sess[provenance_key] = {
                "msg_idx": msg_idx,
                "tag_idx": tag_idx,
                "sql": sql,
                "timestamp": datetime.now().isoformat()
            }
            
            # Create the dataframe tag with semantic ID and provenance
            content = f'<dataframe name="{semantic_id}" table="{table_name}" msg_idx="{msg_idx}" tag_idx="{tag_idx}" >\n'
            content += "\n".join(tsv_output) + "\n"
            content += "</dataframe>\n"
            print(f"DEBUG - Adding dataframe message with content length: {len(content)}")
            add_message(role=USER_ROLE, content=content, db=db)
            
        elif err:
            content = f"<error>\n{err}\n</error>\n"
            add_message(role=USER_ROLE, content=content, db=db)
        
        # Always rerun after processing a SQL query, regardless of result type
        st.rerun()

    if sess.pending_chart:
        chart_tuple = sess.pending_chart.pop(0)
        print(f"DEBUG - chart_tuple: {chart_tuple}")
        chart_idx = chart_tuple[0]
        chart_content = chart_tuple[1]["content"]
        chart_attrs = chart_tuple[1]["attributes"]
        
        # Get the referenced dataframe name from chart attributes
        df_reference = chart_attrs.get("dataframe")
        if not df_reference:
            print("ERROR - Chart missing dataframe reference")
            st.error("Chart missing dataframe reference")
            st.rerun()
        
        # Resolve the dataframe reference to a specific semantic ID
        semantic_id = None
        
        # If a table name is specified, use the latest for that table
        if df_reference in sess.latest_dataframes:
            semantic_id = sess.latest_dataframes[df_reference]
            print(f"DEBUG - Resolved table name '{df_reference}' to semantic ID: {semantic_id}")
        else:
            # If not a known table name, use as-is (might be a direct semantic ID reference)
            semantic_id = df_reference
            print(f"DEBUG - Using reference directly: {semantic_id}")
        
        # Get the provenance information for this dataframe
        provenance_key = f"provenance_{semantic_id}"
        if provenance_key in sess:
            provenance = sess[provenance_key]
            msg_idx = provenance.get("msg_idx")
            tag_idx = provenance.get("tag_idx")
            
            # Create the figure tag with the resolved semantic ID and provenance information
            figure_content = f'<figure dataframe="{semantic_id}" msg_idx="{msg_idx}" tag_idx="{tag_idx}" title="{chart_attrs.get("title", "Chart")}">\n{chart_content}\n</figure>'
            print(f"DEBUG - Creating figure with resolved dataframe: {semantic_id}")
            
            # Add the figure message
            add_message(role=ASSISTANT_ROLE, content=figure_content, db=db)
        else:
            print(f"ERROR - No provenance information found for dataframe: {semantic_id}")
            st.error(f"Could not find dataframe: {semantic_id}")
        
        st.rerun()

    if sess.pending_response:
        sess.pending_response = False
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
        prompt_template = ChatPromptTemplate.from_messages(sess.lc_messages)
        processing_pipeline = prompt_template | llm | StrOutputParser()
        response = "".join(processing_pipeline.stream({}))
        add_message(role=ASSISTANT_ROLE, content=response, db=db)
        msg = get_elements(response)
        sess.pending_sql = list(enumerate(msg.get("sql", [])))
        print(f"DEBUG - pending_sql: {sess.pending_sql}")
        sess.pending_chart = list(enumerate(msg.get("chart", [])))       
        st.rerun()
        
    if input := st.chat_input("Type your message..."):
        add_message(role=USER_ROLE, content=input, db=db)
        sess.pending_response = True
        if re.match(SQL_REGEX, input.strip(), re.IGNORECASE):
            input = "<sql>\n" + input + "\n</sql>\n"
        msg = get_elements(input)
        if msg.get("sql"):
            sess.pending_sql = list(enumerate(msg.get("sql", [])))
        st.rerun()
