from datetime import datetime
import os
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
        if 'logfile' not in st.session_state:
            self._init_logging()
        
    def _init_logging(self):
        """Initialize logging for the conversation."""
        log_dir = f"logs/{datetime.now().strftime('%m-%d')}"
        os.makedirs(log_dir, exist_ok=True)
        st.session_state.logfile = open(f"{log_dir}/{datetime.now().strftime('%H-%M')}.log", "w")
        
    def log(self, role: str, message: str):
        """Write a message to the conversation log."""
        if role in [USER_ROLE, ASSISTANT_ROLE] and 'logfile' in st.session_state:
            st.session_state.logfile.write(f"\n{role.capitalize()}\n {message}\n")
            st.session_state.logfile.flush()

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

    def _load_conversation(self, conv_id):
        """Helper method to load a conversation and update session state"""
        sess = st.session_state
        sess.current_conversation_id = conv_id
        sess.db_messages = self.db.load_messages(conv_id)
        sess.llm_handler = LLMHandler(sess.prompts, self.db)
        # Load messages into LLM handler
        for msg in sess.db_messages:
            sess.llm_handler.add_message(msg["role"], msg["content"])

    def render_sidebar(self):
        """Render the conversation sidebar and handle conversation management"""
        st.sidebar.title("Conversations")
        
        # Dev mode toggle
        if 'dev_mode' not in st.session_state:
            st.session_state.dev_mode = False
        st.session_state.dev_mode = st.sidebar.toggle("Developer Mode", value=st.session_state.dev_mode)
        st.sidebar.divider()
        
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
        if st.sidebar.button("+ New Chat", type="secondary", use_container_width=True):
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
            if self._initialize_new_conversation() is None:
                st.sidebar.error("Failed to create new conversation")
                return
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
                title = conv['title']
                button_type = "primary" if is_active else "secondary"
                if st.button(title, key=f"conv_{conv['id']}", use_container_width=True, type=button_type):
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
                        self._load_conversation(conv['id'])
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
                        if st.button("❎ Training" if not conv['is_flagged_for_training'] else "✅ Training", 
                                   key=f"flag_{conv['id']}", 
                                   type="secondary"):
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
        self.log(role, content)

    def _initialize_new_conversation(self, title="New Chat"):
        """Initialize a new conversation with common setup code"""
        # Create new conversation
        conv_id = self.db.create_conversation(title)
        if conv_id is None:
            return None
            
        # Set up session state
        sess = st.session_state
        sess.current_conversation_id = conv_id
        sess.db_messages = []
        sess.llm_handler = LLMHandler(sess.prompts, self.db)
        
        # Add system prompt as first message
        system_prompt = sess.llm_handler.get_system_prompt(self.db)
        self.add_message(role=SYSTEM_ROLE, content=system_prompt)
        
        # Add welcome message
        self.add_message(role=ASSISTANT_ROLE, content=sess.prompts["welcome_message"])
        
        return conv_id

    def init_session_state(self):
        """Initialize session state with a new conversation"""
        sess = st.session_state
        sess.prompts = get_prompts()
        
        # Get existing conversations
        conversations = self.db.get_conversations()
        
        # Only create a new conversation if there are none
        if not conversations:
            if self._initialize_new_conversation() is None:
                st.error("Failed to create initial conversation")
                return
        else:
            # Use the most recent conversation
            latest_conv = conversations[0]  # Assuming conversations are ordered by recency
            self._load_conversation(latest_conv['id'])
            
        # Initialize other session state variables
        sess.pending_chart = False
        sess.pending_sql = False
        sess.pending_response = False
        sess.table_counters = {}
        sess.latest_dataframes = {} 