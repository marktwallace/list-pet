import duckdb
import streamlit as st
import re
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

def title_text(input):
    return input[:90] + "..." if len(input) > 60 else input

def main():
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
                    with st.expander(title_text(attributes.get("name")), expanded=False):
                        key = "dataframe_" + attributes.get("name")
                        if key in sess:
                            df = sess[key]
                            print(f"DEBUG - Found dataframe in session state, displaying with shape: {df.shape}")  
                            st.dataframe(df, use_container_width=True, hide_index=True)
                        else:
                            print(f"DEBUG - Dataframe not found in session state with key: {key}")
                            msg_idx = attributes.get("msg_idx")
                            tag_idx = attributes.get("tag_idx")
                            if msg_idx is not None and tag_idx is not None:
                                print(f"DEBUG - Have msg_idx: {msg_idx} and tag_idx: {tag_idx}")
                                msg_ref_content = sess.db_messages[msg_idx]["content"]
                                msg_ref = get_elements(msg_ref_content)
                                if arr := msg_ref.get("sql",[]) and tag_idx < len(arr):
                                    sql = arr[tag_idx]
                                    button_clicked = st.button(
                                        "Regenerate Dataframe",
                                        key=f"df_btn_{idx}",
                                        type="primary",
                                        use_container_width=True,
                                    )
                                else:
                                    st.error("Missing sql for dataframe regeneration")
                            else:
                                st.error("Missing msg_idx or tag_idx for dataframe")

            if "error" in msg:
                for item in msg["error"]:
                    with st.expander(title_text(item["content"]), expanded=False):
                        st.code(item["content"])


            # title, chart, chart_key = get_chart(message, sess)
            # if title:
            #     with st.expander(title, expanded=False):
            #         if chart:
            #             st.plotly_chart(chart, use_container_width=True, key=chart_key)
            #         else:
            #             button_clicked = st.button(
            #                 "Regenerate Chart",
            #                 key=f"chart_btn_{idx}",
            #                 type="primary",
            #                 use_container_width=True,
            #             )

    # Handle Button Clicks
    for idx, message in enumerate(sess.db_messages):
        msg = get_elements(message["content"])

        if sess.get(f"df_btn_{idx}"):
            sess[f"df_btn_{idx}"] = False
            sql = sess[f"df_btn_{idx}_sql"]
            df,err = db.execute_query(sql)
            if err:
                print(f"ERROR - {err} for dataframe regeneration while rerunning SQL: {sql} ")
            else:
                sess["dataframe_" + attributes.get("name")] = df
                st.rerun()

        # if sess.get(f"chart_btn_{idx}"):
        #     sess[f"chart_btn_{idx}"] = False
        #     st.write(f"Regenerating Chart for message {idx}...")
        #     new_chart = regenerate_chart(message, sess)
        #     st.rerun()

    if sess.pending_sql:
        # pop one sql message from the list, process it, then rerun()
        sql_tuple = sess.pending_sql.pop(0)
        print(f"DEBUG - sql_tuple: {sql_tuple}")
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
            msg_idx = len(sess.db_messages) - 1
            content = f'<dataframe name="{table_name}" msg_idx="{msg_idx}" tag_idx="{sql_tuple[0]}" >\n'
            content += "\n".join(tsv_output) + "\n"
            content += "</dataframe>\n"
            print(f"DEBUG - Adding dataframe message with content length: {len(content)}")
            add_message(role=USER_ROLE, content=content, db=db)
            print(f"DEBUG - Storing dataframe in session state with key: dataframe_{table_name}")
            sess["dataframe_" + table_name] = df
        elif err:
            content = f"<error>\n{err}\n</error>\n"
            add_message(role=USER_ROLE, content=content, db=db)
        
        # Always rerun after processing a SQL query, regardless of result type
        st.rerun()

    # if sess.pending_chart:
    #     chart = sess.pending_chart.pop(0)
    #     # response = generate_chart(chart)
    #     # add_message(role=USER_ROLE, content=response)
    #     # st.rerun()

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
