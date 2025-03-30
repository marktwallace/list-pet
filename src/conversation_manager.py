from datetime import datetime
import streamlit as st

from .database import Database
from .llm_handler import LLMHandler
from .parsing import get_elements
from .prompt_loader import get_prompts

# Define roles
USER_ROLE = "user"
ASSISTANT_ROLE = "assistant"
SYSTEM_ROLE = "system"

class ConversationManager:
    def __init__(self, db: Database):
        self.db = db
        
    def title_text(self, input):
        """Helper function to truncate titles"""
        return input[:90] + "..." if len(input) > 60 else input
        
    def extract_user_content(self, messages):
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

    def generate_conversation_title(self, messages):
        """Generate a title for a conversation based on its messages"""
        if not messages:
            print("DEBUG - No messages provided for title generation")
            return None
            
        # Extract user messages
        user_content = self.extract_user_content(messages)
        if not user_content:
            print("DEBUG - No user content extracted for title generation")
            return None
        
        return st.session_state.llm_handler.generate_title(user_content)

    def render_sidebar(self):
        """Render the conversation sidebar and handle conversation management"""
        st.sidebar.title("Conversations")
        
        # Get all conversations first
        conversations = self.db.get_conversations()
        
        # Process any pending renames from previous switch
        pending_renames = [k for k in st.session_state.keys() if k.startswith("pending_rename_")]
        if pending_renames:
            print(f"DEBUG - Found pending renames: {pending_renames}")
            pending_key = pending_renames[0]
            conv_id = int(pending_key.split("_")[-1])
            print(f"DEBUG - Processing rename for conversation {conv_id}")
            
            # Generate and apply the new name
            messages = self.db.load_messages(conv_id)
            print(f"DEBUG - Loaded {len(messages)} messages for rename")
            new_title = self.generate_conversation_title(messages)
            print(f"DEBUG - Generated new title: {new_title}")
            
            if new_title:
                self.db.update_conversation(conv_id, title=new_title)
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
                messages = self.db.load_messages(current_conv['id'])
                print(f"DEBUG - Loaded {len(messages)} messages for rename")
                new_title = self.generate_conversation_title(messages)
                print(f"DEBUG - Generated new title: {new_title}")
                
                if new_title:
                    self.db.update_conversation(current_conv['id'], title=new_title)
                    print(f"DEBUG - Updated conversation {current_conv['id']} with new title: {new_title}")
            
            # Create new conversation and reset state
            conv_id = self.db.create_conversation("New Chat")
            if conv_id is None:
                st.sidebar.error("Failed to create new conversation")
                return
            
            st.session_state.current_conversation_id = conv_id
            st.session_state.db_messages = []
            st.session_state.llm_handler = LLMHandler(st.session_state.prompts)
            self.add_message(role=SYSTEM_ROLE, content=st.session_state.prompts["welcome_message"])
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
                        st.session_state.db_messages = self.db.load_messages(conv['id'])
                        print(f"DEBUG - Switched to conversation {conv['id']}")
                        st.session_state.llm_handler = LLMHandler(st.session_state.prompts)
                        for msg in st.session_state.db_messages:
                            if msg["role"] == USER_ROLE:
                                st.session_state.llm_handler.add_message(USER_ROLE, msg["content"])
                            elif msg["role"] == ASSISTANT_ROLE:
                                st.session_state.llm_handler.add_message(ASSISTANT_ROLE, msg["content"])
                            elif msg["role"] == SYSTEM_ROLE:
                                st.session_state.llm_handler.add_message(SYSTEM_ROLE, msg["content"])
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
                        self.db.update_conversation(conv['id'], title=new_title)
                        st.rerun()
                    
                    # Training data flags
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("🏁 Flag" if not conv['is_flagged_for_training'] else "✅ Flagged", 
                                   key=f"flag_{conv['id']}", 
                                   type="primary" if not conv['is_flagged_for_training'] else "secondary"):
                            self.db.update_conversation(conv['id'], is_flagged=not conv['is_flagged_for_training'])
                            st.rerun()
                    
                    with col2:
                        if st.button("🗑️ Archive" if not conv['is_archived'] else "📥 Restore",
                                   key=f"arch_{conv['id']}", 
                                   type="secondary"):
                            self.db.update_conversation(conv['id'], is_archived=not conv['is_archived'])
                            st.rerun()
                    
                    # Close options
                    if st.button("Close", key=f"close_{conv['id']}", use_container_width=True):
                        st.session_state[f"show_options_{conv['id']}"] = False
                        st.rerun()

    def add_message(self, role, content):
        """Add a message to the current conversation"""
        message = {"role": role, "content": content}
        st.session_state.db_messages.append(message)
        self.db.log_message(message, st.session_state.current_conversation_id)
        st.session_state.llm_handler.add_message(role, content)

    def init_session_state(self):
        """Initialize session state with a new conversation"""
        sess = st.session_state
        sess.prompts = get_prompts()
        sess.llm_handler = LLMHandler(sess.prompts)
        
        # Always create a new conversation for fresh session
        conv_id = self.db.create_conversation("New Chat")
        if conv_id is None:
            st.error("Failed to create initial conversation")
            return
            
        sess.current_conversation_id = conv_id
        sess.db_messages = []
        self.add_message(role=SYSTEM_ROLE, content=sess.prompts["welcome_message"])
        
        sess.pending_chart = False
        sess.pending_sql = False
        sess.pending_response = False
        sess.table_counters = {}
        sess.latest_dataframes = {} 