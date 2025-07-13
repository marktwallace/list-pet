from datetime import datetime
import os
import streamlit as st
import sys
import re

from .metadata_database import MetadataDatabase
from .llm_handler import LLMHandler
from .parsing import get_elements
from .prompt_loader import get_prompts
from .ui_styles import TRAIN_ICON

# Define roles
USER_ROLE = "user"
ASSISTANT_ROLE = "assistant"
SYSTEM_ROLE = "system"

class ConversationManager:
    def __init__(self, metadata_db: MetadataDatabase):
        self.metadata_db = metadata_db
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
        sess.db_messages = self.metadata_db.load_messages(conv_id)
        # Pass model name from environment, defaulting if not set
        openai_model_name = os.environ.get("OPENAI_MODEL_NAME") # LLMHandler will apply its own default if this is None
        sess.llm_handler = LLMHandler(sess.prompts, self.metadata_db, model_name=openai_model_name)
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
        
        # Add Export Training button in dev mode
        if st.session_state.dev_mode:
            if st.sidebar.button("Export Training", type="secondary", use_container_width=True):
                exported_count, timestamp = self.export_training_data()
                if exported_count > 0:
                    st.sidebar.success(f"✅ Exported {exported_count} conversations to training/{timestamp}/")
                else:
                    st.sidebar.warning("No conversations flagged for training found.")
        
        # Show analytic database status
        if hasattr(st.session_state, 'analytic_db') and st.session_state.analytic_db:
            info = st.session_state.analytic_db.get_connection_info()
            db_type = info.get('type', 'Unknown')
            if info.get('connected', False):
                st.sidebar.success(f"📊 {db_type} Connected")
            else:
                st.sidebar.error(f"📊 {db_type} Disconnected")
        else:
            st.sidebar.warning("📊 No Analytic DB")
        
        st.sidebar.divider()
        
        # Get all conversations first
        conversations = self.metadata_db.get_conversations()
        
        # Process any pending renames from previous switch
        pending_renames = [k for k in st.session_state.keys() if k.startswith("pending_rename_")]
        if pending_renames:
            print(f"DEBUG - Found pending renames: {pending_renames}")
            pending_key = pending_renames[0]
            conv_id = int(pending_key.split("_")[-1])
            print(f"DEBUG - Processing rename for conversation {conv_id}")
            
            # Generate and apply the new name
            messages = self.metadata_db.load_messages(conv_id)
            print(f"DEBUG - Loaded {len(messages)} messages for rename")
            new_title = self.generate_conversation_title(messages)
            print(f"DEBUG - Generated new title: {new_title}")
            
            if new_title:
                self.metadata_db.update_conversation(conv_id, title=new_title)
                print(f"DEBUG - Updated conversation {conv_id} with new title: {new_title}")
            else:
                print(f"DEBUG - No new title generated for conversation {conv_id}")
            
            # Clear the pending state
            del st.session_state[pending_key]
            print(f"DEBUG - Cleared pending rename state: {pending_key}")
            st.rerun()
        
        # New chat button
        if st.sidebar.button("+ New Conversation", key="new-conversation-button", type="secondary", use_container_width=True, kwargs={"class": "new-conversation-button"}):
            # Check if current conversation needs renaming
            current_conv = next((c for c in conversations if c['id'] == st.session_state.current_conversation_id), None)
            if current_conv and current_conv['title'] == "Unlabeled Chat":
                # Process the rename immediately instead of queuing
                print(f"DEBUG - Processing rename for conversation {current_conv['id']} before creating new chat")
                messages = self.metadata_db.load_messages(current_conv['id'])
                print(f"DEBUG - Loaded {len(messages)} messages for rename")
                new_title = self.generate_conversation_title(messages)
                print(f"DEBUG - Generated new title: {new_title}")
                
                if new_title:
                    self.metadata_db.update_conversation(current_conv['id'], title=new_title)
                    print(f"DEBUG - Updated conversation {current_conv['id']} with new title: {new_title}")
            
            # Create new conversation and reset state
            if self._initialize_new_conversation() is None:
                st.sidebar.error("Failed to create new conversation")
                return
            st.rerun()
        
        # Show database timestamp
        if hasattr(st.session_state, 'analytic_db') and st.session_state.analytic_db:
            timestamp = st.session_state.analytic_db.get_timestamp()
            st.sidebar.info(f"Data updated: {timestamp}")
        
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
                if conv['is_flagged_for_training']:
                    title = f"{TRAIN_ICON} {title}"
                button_type = "primary" if is_active else "secondary"
                if st.button(title, key=f"conv_{conv['id']}", use_container_width=True, type=button_type):
                    if not is_active:
                        # Check if we're switching away from a "New Chat"
                        current_conv = next((c for c in conversations if c['id'] == st.session_state.current_conversation_id), None)
                        print(f"DEBUG - Current conversation before switch: {current_conv}")
                        if current_conv and current_conv['title'] == "Unlabeled Chat":
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
                        self.metadata_db.update_conversation(conv['id'], title=new_title)
                        st.rerun()
                    
                    # Training data flags
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("☐ Training" if not conv['is_flagged_for_training'] else "✅ Training", 
                                   key=f"flag_{conv['id']}", 
                                   type="secondary"):
                            self.metadata_db.update_conversation(conv['id'], is_flagged=not conv['is_flagged_for_training'])
                            st.rerun()
                    
                    with col2:
                        if st.button("🗑️ Archive" if not conv['is_archived'] else "📥 Restore",
                                   key=f"arch_{conv['id']}", 
                                   type="secondary"):
                            self.metadata_db.update_conversation(conv['id'], is_archived=not conv['is_archived'])
                            st.rerun()
                    
                    # Close options
                    if st.button("Close", key=f"close_{conv['id']}", use_container_width=True):
                        st.session_state[f"show_options_{conv['id']}"] = False
                        st.rerun()

    def add_message(self, role, content):
        """Add a message to the current conversation, log it, and update session state."""
        message_to_log = {"role": role, "content": content}
        
        # Log the message to the database and get the new ID
        new_id = self.metadata_db.log_message(message_to_log, st.session_state.current_conversation_id)
        
        if new_id is None:
            # Handle logging failure
            st.error("Failed to save message. Please try again.")
            return

        # Create the full message object for session state
        message_for_session = {
            "id": new_id,
            "role": role,
            "content": content,
            "feedback_score": 0  # Default score for a new message
        }

        # Append to session state and log to file
        st.session_state.db_messages.append(message_for_session)
        st.session_state.llm_handler.add_message(role, content)
        self.log(role, content)

    def _initialize_new_conversation(self, title="Unlabeled Chat"):
        """Initialize a new conversation with common setup code"""
        # Create new conversation
        conv_id = self.metadata_db.create_conversation(title)
        if conv_id is None:
            return None
            
        # Set up session state
        sess = st.session_state
        sess.current_conversation_id = conv_id
        sess.db_messages = []
        # Pass model name from environment, defaulting if not set
        openai_model_name = os.environ.get("OPENAI_MODEL_NAME") # LLMHandler will apply its own default if this is None
        sess.llm_handler = LLMHandler(sess.prompts, self.metadata_db, model_name=openai_model_name)
        
        # Add system prompt as first message
        system_prompt = sess.llm_handler.get_system_prompt()
        self.add_message(role=SYSTEM_ROLE, content=system_prompt)
        
        # Add welcome message
        self.add_message(role=ASSISTANT_ROLE, content=sess.prompts["welcome_message"])
        
        return conv_id

    def export_training_data(self):
        """Export conversations flagged for training to text files."""
        # Get base path from session state
        base_path = st.session_state.get('config_base_path', '.')
        
        # Create timestamped directory under training/
        timestamp = datetime.now().strftime('%m-%d-%H-%M')
        export_dir = os.path.join(base_path, "training", timestamp)
        os.makedirs(export_dir, exist_ok=True)
        
        # Get system prompt for separate file
        system_prompt = st.session_state.llm_handler.get_system_prompt()
        
        # Write system prompt to separate file
        system_prompt_path = os.path.join(export_dir, "System Prompt.txt")
        with open(system_prompt_path, 'w', encoding='utf-8') as f:
            f.write(system_prompt)
        
        # Get all conversations flagged for training
        conversations = self.metadata_db.get_conversations(include_archived=True)
        exported_count = 0
        
        for conv in conversations:
            if not conv['is_flagged_for_training']:
                continue
                
            # Load messages for this conversation
            messages = self.metadata_db.load_messages(conv['id'])
            if not messages:
                continue
                
            # Create file with conversation title as name
            filename = f"{conv['title']}.txt"
            filepath = os.path.join(export_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for idx, msg in enumerate(messages):
                    # Skip the first message if it's a system message
                    if idx == 0 and msg['role'] == 'system':
                        continue
                    
                    # Write role on its own line
                    f.write(f"{msg['role'].capitalize()}:\n")
                    # Write message content
                    f.write(f"{msg['content']}\n\n")
            
            exported_count += 1
            
        return exported_count, timestamp

    def init_session_state(self):
        """Initialize session state with a new conversation"""
        sess = st.session_state
        # Ensure config_base_path is available (should be set by streamlit_ui.py)
        if 'config_base_path' not in sess:
            # This is a fallback, should ideally be set by the entry script
            print("WARNING: config_base_path not found in session_state, defaulting to '.' for get_prompts.", file=sys.stderr)
            sess.config_base_path = "."
            
        sess.prompts = get_prompts(sess.config_base_path)
        
        # --- Check for required prompt files --- START --- 
        required_prompt_keys = ["system_prompt", "title", "welcome_message"]
        missing_prompts_details = []
        prompts_dir_path = os.path.join(sess.config_base_path, 'prompts') # For the error message

        for key in required_prompt_keys:
            if key not in sess.prompts or not sess.prompts[key]: # Also check if prompt content is empty
                # Try to determine common extensions for the error message
                possible_filenames = [f"{key}.txt", f"{key}.md", f"{key}.yaml", f"{key}"] 
                missing_prompts_details.append(f"- '{key}' (expected as e.g., {', '.join(possible_filenames[:-1])} or {possible_filenames[-1]} in {prompts_dir_path}) - Content might be missing or file not found.")

        if missing_prompts_details:
            error_message_lines = [
                f"Critical Startup Error: Missing Required Prompt Files",
                f"The application cannot start because the following essential prompt files were not found or are empty in the directory: '{prompts_dir_path}'",
                "Please ensure these files exist and contain the necessary prompt text:",
                *missing_prompts_details,
                "Example expected files: system_prompt.txt, title.txt, welcome_message.txt"
            ]
            full_error_message = "\n".join(error_message_lines)
            
            st.error(full_error_message)
            # Correctly format the message for console logging with escaped newlines
            console_friendly_message = full_error_message.replace('\n', r'\n') # Use raw string for replacement
            print(f"ERROR - {console_friendly_message}", file=sys.stderr)
            st.stop() # Halt Streamlit execution
        # --- Check for required prompt files --- END --- 
        
        # Get existing conversations
        conversations = self.metadata_db.get_conversations()
        
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
        if "pending_response" not in sess:
            sess.pending_response = False
        if "pending_sql" not in sess:
            sess.pending_sql = []
        if "pending_chart" not in sess:
            sess.pending_chart = []
        if "pending_python" not in sess:
            sess.pending_python = []
        if "table_counters" not in sess:
            sess.table_counters = {}
        if "latest_dataframes" not in sess:
            sess.latest_dataframes = {}
        if "dev_mode" not in sess:
            sess.dev_mode = False
        if "editing_message_id" not in sess:
            sess.editing_message_id = None
        if "pending_completion" not in sess:
            sess.pending_completion = None
        if "llm_handler" not in sess:
            # Ensure prompts are loaded before LLMHandler initialization if it happens here
            if 'prompts' not in sess:
                sess.prompts = get_prompts(sess.config_base_path)
            openai_model_name = os.environ.get("OPENAI_MODEL_NAME")
            sess.llm_handler = LLMHandler(sess.prompts, self.metadata_db, model_name=openai_model_name) 