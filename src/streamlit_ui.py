from datetime import datetime
import os
import re
import traceback

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
    db.log_message(message, st.session_state.current_conversation_id)
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
    """Initialize session state with a new conversation"""
    sess.prompts = get_prompts()
    sess.lc_messages = [SystemMessagePromptTemplate.from_template(sess.prompts["system_prompt"])]
    
    # Always create a new conversation for fresh session
    conv_id = db.create_conversation("New Chat")
    if conv_id is None:
        st.error("Failed to create initial conversation")
        return
        
    sess.current_conversation_id = conv_id
    sess.db_messages = []
    add_message(role=SYSTEM_ROLE, content=sess.prompts["welcome_message"], db=db)
    
    sess.pending_chart = False
    sess.pending_sql = False
    sess.pending_response = False
    sess.table_counters = {}
    sess.latest_dataframes = {}

def title_text(input):
    return input[:90] + "..." if len(input) > 60 else input

def validate_element_indices(attributes, required_attrs, element_type="element"):
    """
    Validates and converts message and tag indices from attributes.
    Returns (msg_idx, tag_idx) tuple or (None, None) if validation fails.
    """
    for attr_msg, attr_tag, desc in required_attrs:
        if attr_msg not in attributes or attr_tag not in attributes:
            st.error(f"Missing {desc} message or tag index for {element_type}")
            return None, None
            
        try:
            msg_idx = int(attributes[attr_msg])
            tag_idx = int(attributes[attr_tag])
            return msg_idx, tag_idx
        except (ValueError, IndexError) as e:
            st.error(f"Error processing {desc} indices: {str(e)}")
            return None, None

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
    dataframe_name = attributes["name"]
    display_name = attributes.get("display_name", attributes.get("table", dataframe_name))
    
    with st.expander(title_text(display_name), expanded=True):
        key = "dataframe_" + dataframe_name
        if key in sess:
            df = sess[key]
            st.dataframe(df, use_container_width=True, hide_index=True)
            return
        
        # Validate indices
        sql_msg_idx, sql_tag_idx = validate_element_indices(
            attributes,
            [("sql_msg_idx", "sql_tag_idx", "SQL")],
            "dataframe"
        )
        if sql_msg_idx is None:
            return
            
        msg_ref_content = sess.db_messages[sql_msg_idx]["content"]
        msg_ref = get_elements(msg_ref_content)
        arr = msg_ref.get("sql", [])
        
        if arr and sql_tag_idx < len(arr):
            sql = arr[sql_tag_idx]["content"]
            button_key = f"df_btn_{idx}_{sql_msg_idx}_{sql_tag_idx}"
            handle_regenerate_button(button_key, sql, db, key)
        else:
            st.error("Missing sql for dataframe regeneration")

def get_figure_key(idx, dataframe_name, chart_content):
    """Generate a unique figure key based on index, dataframe name and chart content"""
    content_hash = hash(chart_content) % 100000  # Keep it to 5 digits
    return f"figure_{idx}_{dataframe_name}_{content_hash}"

def display_figure_item(item, idx, sess, db):
    """Display a figure element with its expander and regeneration button if needed"""
    content = item["content"]
    attributes = item["attributes"]
    dataframe_name = attributes["dataframe"]
    dataframe_key = "dataframe_" + dataframe_name
    
    # Validate both SQL and chart indices
    sql_msg_idx, sql_tag_idx = validate_element_indices(
        attributes,
        [("sql_msg_idx", "sql_tag_idx", "SQL")],
        "figure"
    )
    if sql_msg_idx is None:
        return
        
    chart_msg_idx, chart_tag_idx = validate_element_indices(
        attributes,
        [("chart_msg_idx", "chart_tag_idx", "chart")],
        "figure"
    )
    if chart_msg_idx is None:
        return
    
    # Get SQL array from message content
    sql_msg_content = sess.db_messages[sql_msg_idx]["content"]
    sql_elements = get_elements(sql_msg_content)
    sql_arr = sql_elements.get("sql", [])
    
    # Create a unique figure key using the chart content
    chart_msg = sess.db_messages[chart_msg_idx]["content"]
    msg_elements = get_elements(chart_msg)
    chart_arr = msg_elements.get("chart", [])
    
    if not chart_arr or chart_tag_idx >= len(chart_arr):
        st.error("Could not find chart configuration in message history")
        return
        
    chart_content = chart_arr[chart_tag_idx]["content"]
    figure_key = get_figure_key(idx, dataframe_name, chart_content)
    
    # Use the figure content as the title (it should contain only the title text)
    title = content.strip()
    
    # Fallback if title is empty
    if not title:
        display_name = dataframe_name.split("_")[0] if "_" in dataframe_name else dataframe_name
        title = f"Chart for {display_name}"
    
    with st.expander(title_text(title), expanded=True):
        # If dataframe exists, render chart or retrieve from cache
        if dataframe_key in sess:
            # Check if figure is already cached in session state
            if figure_key in sess:
                cached = sess[figure_key]
                if "error" in cached:
                    st.error(f"Error rendering chart: {cached['error']}")
                    st.dataframe(sess[dataframe_key], use_container_width=True, hide_index=True)
                else:
                    st.plotly_chart(cached["figure"], use_container_width=True, key=figure_key)
            else:
                # If not cached, render it now (this should rarely happen after our changes)
                df = sess[dataframe_key]
                fig, err = render_chart(df, chart_content)
                if err:
                    sess[figure_key] = {"error": err}
                    st.error(f"Error rendering chart: {err}")
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    sess[figure_key] = {"figure": fig}
                    st.plotly_chart(fig, use_container_width=True, key=figure_key)
            return
        
        # Dataframe doesn't exist, show regeneration button
        st.info(f"The dataframe '{dataframe_name}' is not available. Click the button below to regenerate it.")
        
        if sql_arr and sql_tag_idx < len(sql_arr):
            sql = sql_arr[sql_tag_idx]["content"]
            button_key = f"fig_btn_{idx}_{sql_msg_idx}_{sql_tag_idx}"
            if handle_regenerate_button(button_key, sql, db, dataframe_key):
                # Clear the cached figure when regenerating the dataframe
                if figure_key in sess:
                    del sess[figure_key]
        else:
            st.error("Missing SQL for figure dataframe regeneration")

def process_sql_query(sql_tuple, db):
    """Process an SQL query and store results as a dataframe"""
    sess = st.session_state
    sql_idx, sql_item = sql_tuple
    sql = sql_item["content"]
    msg_idx = len(sess.db_messages) - 1 
    # this is the index of the current message being processed, 
    # which is an assistant or user message with a sql tag

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
    
    dataframe_name = f"{table_name}_{sess.table_counters[table_name]}"
    sess.latest_dataframes[table_name] = dataframe_name
    
    # Store dataframe in session state
    dataframe_key = f"dataframe_{dataframe_name}"
    sess[dataframe_key] = df
    
    # Format preview for display
    preview_rows = min(5, len(df)) if len(df) > 20 else len(df)
    tsv_lines = ["\t".join(df.columns)]
    tsv_lines.extend("\t".join(str(val) for val in row) for _, row in df.iloc[:preview_rows].iterrows())
    if preview_rows < len(df):
        tsv_lines.append("...")
    
    # Create and add dataframe message
    content = f'<dataframe name="{dataframe_name}" table="{table_name}" sql_msg_idx="{msg_idx}" sql_tag_idx="{sql_idx}" >\n'
    content += "\n".join(tsv_lines) + "\n</dataframe>\n"
    
    print(f"DEBUG - Adding dataframe with name: {dataframe_name}")
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
        add_message(role=USER_ROLE, content="<error>\nChart missing dataframe reference\n</error>\n", db=Database())
        return True
    
    # Resolve dataframe reference (table name or direct dataframe name)
    dataframe_name = sess.latest_dataframes.get(df_reference, df_reference)
    
    # Find the dataframe and its SQL indices
    def find_dataframe_sql_indices():
        for i, msg in enumerate(reversed(sess.db_messages)):
            msg_elements = get_elements(msg["content"])
            if "dataframe" in msg_elements:
                for df_item in msg_elements["dataframe"]:
                    if df_item["attributes"].get("name") == dataframe_name:
                        msg_idx_str = df_item["attributes"].get("sql_msg_idx")
                        tag_idx_str = df_item["attributes"].get("sql_tag_idx")
                        if msg_idx_str is not None and tag_idx_str is not None:
                            return int(msg_idx_str), int(tag_idx_str)
        return None, None
    
    sql_msg_idx, sql_tag_idx = find_dataframe_sql_indices()
    if sql_msg_idx is None or sql_tag_idx is None:
        add_message(role=USER_ROLE, content=f"<error>\nCould not find dataframe '{dataframe_name}' in message history\n</error>\n", db=Database())
        return True
    
    # Find the most recent assistant message containing a chart tag
    def find_chart_message():
        for i, msg in enumerate(reversed(sess.db_messages)):
            if msg["role"] == ASSISTANT_ROLE:
                msg_elements = get_elements(msg["content"])
                if "chart" in msg_elements:
                    return len(sess.db_messages) - 1 - i
        return None
    
    chart_msg_idx = find_chart_message()
    if chart_msg_idx is None:
        add_message(role=USER_ROLE, content="<error>\nCould not find assistant message with chart configuration\n</error>\n", db=Database())
        return True
        
    print(f"DEBUG - Chart configuration in message {chart_msg_idx} (role={sess.db_messages[chart_msg_idx]['role']})")
    print(f"DEBUG - SQL in message {sql_msg_idx} (role={sess.db_messages[sql_msg_idx]['role']})")
    
    # Attempt to render the chart to validate configuration
    dataframe_key = "dataframe_" + dataframe_name
    if dataframe_key in sess:
        df = sess[dataframe_key]
        fig, err = render_chart(df, chart_content)
        figure_key = get_figure_key(chart_idx, dataframe_name, chart_content)
        
        if err:
            # Cache the error
            sess[figure_key] = {"error": err}
            add_message(role=USER_ROLE, content=f"<error>\nError rendering chart: {err}\n</error>\n", db=Database())
            return True
        else:
            # Cache the successful figure
            sess[figure_key] = {"figure": fig}
    
    # Extract title from chart content if available
    title = None
    title_match = re.search(r'title:\s*(.*?)$', chart_content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        # Fallback title
        title = f"Chart for {dataframe_name.split('_')[0]}"
    
    # Create figure content with title in content and all indices in attributes
    figure_content = (
        f'<figure dataframe="{dataframe_name}" sql_msg_idx="{sql_msg_idx}" sql_tag_idx="{sql_tag_idx}" '
        f'chart_msg_idx="{chart_msg_idx}" chart_tag_idx="{chart_idx}">\n'
        f'{title}\n'
        f'</figure>'
    )
    
    print(f"DEBUG - Creating figure for dataframe: {dataframe_name}")
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

def render_conversation_sidebar(db):
    """Render the conversation sidebar and handle conversation management"""
    st.sidebar.title("Conversations")
    
    # Get all conversations first
    conversations = db.get_conversations()
    
    # Process any pending renames from previous switch
    pending_renames = [k for k in st.session_state.keys() if k.startswith("pending_rename_")]
    if pending_renames:
        print(f"DEBUG - Found pending renames: {pending_renames}")
        pending_key = pending_renames[0]
        conv_id = int(pending_key.split("_")[-1])
        print(f"DEBUG - Processing rename for conversation {conv_id}")
        
        # Generate and apply the new name
        messages = db.load_messages(conv_id)
        print(f"DEBUG - Loaded {len(messages)} messages for rename")
        new_title = generate_conversation_title(messages)
        print(f"DEBUG - Generated new title: {new_title}")
        
        if new_title:
            db.update_conversation(conv_id, title=new_title)
            print(f"DEBUG - Updated conversation {conv_id} with new title: {new_title}")
        else:
            print(f"DEBUG - No new title generated for conversation {conv_id}")
        
        # Clear the pending state
        del st.session_state[pending_key]
        print(f"DEBUG - Cleared pending rename state: {pending_key}")
        st.rerun()
    
    # New chat button
    if st.sidebar.button("+ New Chat", type="primary", use_container_width=True):
        # Check if current conversation needs renaming
        current_conv = next((c for c in conversations if c['id'] == st.session_state.current_conversation_id), None)
        if current_conv and current_conv['title'] == "New Chat":
            # Process the rename immediately instead of queuing
            print(f"DEBUG - Processing rename for conversation {current_conv['id']} before creating new chat")
            messages = db.load_messages(current_conv['id'])
            print(f"DEBUG - Loaded {len(messages)} messages for rename")
            new_title = generate_conversation_title(messages)
            print(f"DEBUG - Generated new title: {new_title}")
            
            if new_title:
                db.update_conversation(current_conv['id'], title=new_title)
                print(f"DEBUG - Updated conversation {current_conv['id']} with new title: {new_title}")
        
        # Create new conversation and reset state
        conv_id = db.create_conversation("New Chat")
        if conv_id is None:
            st.sidebar.error("Failed to create new conversation")
            return
        
        st.session_state.current_conversation_id = conv_id
        st.session_state.db_messages = []
        st.session_state.lc_messages = [SystemMessagePromptTemplate.from_template(st.session_state.prompts["system_prompt"])]
        add_message(role=SYSTEM_ROLE, content=st.session_state.prompts["welcome_message"], db=db)
        st.rerun()
    
    # Display conversations
    if not conversations:
        st.sidebar.info("No conversations found")
        return
    
    # Display conversations
    st.sidebar.divider()
    for conv in conversations:
        col1, col2 = st.sidebar.columns([4, 1])
        
        # Determine if this is the active conversation
        is_active = conv['id'] == st.session_state.current_conversation_id
        
        with col1:
            # Show conversation title with visual indicator if active
            title = "🟢 " + conv['title'] if is_active else conv['title']
            if st.button(title, key=f"conv_{conv['id']}", use_container_width=True):
                if not is_active:
                    # Check if we're switching away from a "New Chat"
                    current_conv = next((c for c in conversations if c['id'] == st.session_state.current_conversation_id), None)
                    print(f"DEBUG - Current conversation before switch: {current_conv}")
                    if current_conv and current_conv['title'] == "New Chat":
                        # Queue the rename operation
                        rename_key = f"pending_rename_{current_conv['id']}"
                        st.session_state[rename_key] = True
                        print(f"DEBUG - Queued rename operation: {rename_key}")
                    
                    # Switch to the selected conversation
                    st.session_state.current_conversation_id = conv['id']
                    st.session_state.db_messages = db.load_messages(conv['id'])
                    print(f"DEBUG - Switched to conversation {conv['id']}")
                    st.session_state.lc_messages = [SystemMessagePromptTemplate.from_template(st.session_state.prompts["system_prompt"])]
                    for msg in st.session_state.db_messages:
                        if msg["role"] == USER_ROLE:
                            st.session_state.lc_messages.append(HumanMessagePromptTemplate.from_template(msg["content"]))
                        elif msg["role"] == ASSISTANT_ROLE:
                            st.session_state.lc_messages.append(AIMessagePromptTemplate.from_template(msg["content"]))
                        elif msg["role"] == SYSTEM_ROLE:
                            st.session_state.lc_messages.append(SystemMessagePromptTemplate.from_template(msg["content"]))
                    st.rerun()
        
        with col2:
            # Show options menu for the conversation
            if st.button("⋮", key=f"opt_{conv['id']}", use_container_width=True):
                st.session_state[f"show_options_{conv['id']}"] = True
        
        # Show options if menu was clicked
        if st.session_state.get(f"show_options_{conv['id']}", False):
            with st.sidebar.expander("Options", expanded=True):
                # Title editing
                new_title = st.text_input("Title", value=conv['title'], key=f"title_{conv['id']}")
                if new_title != conv['title']:
                    db.update_conversation(conv['id'], title=new_title)
                    st.rerun()
                
                # Training data flags
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🏁 Flag" if not conv['is_flagged_for_training'] else "✅ Flagged", 
                               key=f"flag_{conv['id']}", 
                               type="primary" if not conv['is_flagged_for_training'] else "secondary"):
                        db.update_conversation(conv['id'], is_flagged=not conv['is_flagged_for_training'])
                        st.rerun()
                
                with col2:
                    if st.button("🗑️ Archive" if not conv['is_archived'] else "📥 Restore",
                               key=f"arch_{conv['id']}", 
                               type="secondary"):
                        db.update_conversation(conv['id'], is_archived=not conv['is_archived'])
                        st.rerun()
                
                # Close options
                if st.button("Close", key=f"close_{conv['id']}", use_container_width=True):
                    st.session_state[f"show_options_{conv['id']}"] = False
                    st.rerun()

def extract_user_content(messages):
    """Extract clean user message content from messages, excluding SQL/dataframe/figure elements"""
    user_content = []
    print(f"DEBUG - Processing {len(messages)} messages for content extraction")
    for msg in messages:
        if msg["role"] != USER_ROLE:
            continue
        
        # Parse message elements
        elements = get_elements(msg["content"])
        
        # Get markdown content if it exists
        if "markdown" in elements:
            user_content.append(elements["markdown"])
            continue
            
        # Otherwise, use raw content if it doesn't contain any special tags
        content = msg["content"].strip()
        if not any(tag in content for tag in ["<sql>", "<dataframe>", "<figure>", "<error>"]):
            user_content.append(content)
            print(f"DEBUG - Extracted user content: {content[:50]}...")
    
    result = "\n---\n".join(user_content)
    print(f"DEBUG - Final extracted content length: {len(result)} chars")
    return result

def generate_conversation_title(messages):
    """Generate a title for a conversation based on its messages"""
    if not messages:
        print("DEBUG - No messages provided for title generation")
        return None
        
    # Extract user messages
    user_content = extract_user_content(messages)
    if not user_content:
        print("DEBUG - No user content extracted for title generation")
        return None
    
    print(f"DEBUG - Generating title from {len(user_content)} chars of content")
    
    # Create prompt for title generation
    prompt = f"""Based on this conversation:
{user_content}

Create a brief, descriptive title that captures its main topic or intent.
Requirements:
- Maximum 50 characters
- No quotes or special characters
- Should be a clear, concise phrase
- Focus on the main topic or goal discussed
- Do not include words like "Chat about" or "Discussion of"
"""
    
    try:
        # Use the same LLM as the main chat but with different parameters
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
        
        # Create messages in the correct format
        messages = [
            SystemMessagePromptTemplate.from_template(
                "You are a helpful assistant that creates concise, descriptive titles."
            ).format(),
            HumanMessagePromptTemplate.from_template(prompt).format()
        ]
        
        # Use invoke instead of predict
        title = llm.invoke(messages).content
        print(f"DEBUG - Raw title generated: {title}")
        
        # Validate the title meets our requirements
        if len(title) > 80:
            title = title[:77] + "..."
        
        return title
    except Exception as e:
        print(f"ERROR - Failed to generate title: {str(e)}")
        print(f"ERROR - Title generation traceback: {traceback.format_exc()}")
        return None

def main():
    st.set_page_config(page_title="List Pet", page_icon="🐾", layout="wide")
    
    global logfile
    if logfile is None:
        log_dir = f"logs/{datetime.now().strftime('%m-%d')}"
        os.makedirs(log_dir, exist_ok=True)
        logfile = open(f"{log_dir}/{datetime.now().strftime('%H-%M')}.log", "w")
    
    # Initialize database and session state
    sess = st.session_state
    if "conn" not in sess:  # app restart - create new session
        sess.conn = duckdb.connect('db/list_pet.db')
        db = Database()
        db.initialize_pet_meta_schema()
        init_session_state(sess, db)
    else:
        db = Database()
    
    # Render UI
    with st.sidebar:
        render_conversation_sidebar(db)
    
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

