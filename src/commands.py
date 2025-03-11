import json
from datetime import datetime
import streamlit as st
import os
from .constants import ASSISTANT_ROLE, USER_ROLE

def format_messages_example(messages: list, limit: int | None = None) -> str:
    """Format messages in example format, optionally limiting to last N messages."""
    if limit is not None:
        messages = messages[-limit:]
    
    example = []
    for msg in messages:
        content = msg["content"]
        if msg["role"] == USER_ROLE:
            example.append(content)
        elif msg["role"] == ASSISTANT_ROLE:
            example.append(f"{ASSISTANT_ROLE}:\n{content}")
    return "\n\n".join(example) + "\n"

def is_command(text: str) -> tuple[bool, str | None, str | None]:
    """Check if text is a system command and return (is_command, command_type, filename_stem)."""
    text = text.strip().upper()
    if text.startswith("DUMP "):
        parts = text[5:].strip().split()
        
        dump_type = parts[0]
        filename_stem = parts[1] if len(parts) > 1 else None
        
        if dump_type in ["JSON", "EXAMPLE", "TRAIN"]:
            return True, dump_type, filename_stem
        if dump_type.startswith("-"):
            try:
                int(dump_type[1:])
                return True, dump_type, filename_stem
            except ValueError:
                pass
    return False, None, None

def handle_command(command_type: str, command_label: str | None) -> str:
    """Handle system commands and return the result text."""
    # Import here to avoid circular imports
    from .message_manager import get_message_manager
    
    # Get messages from the message manager
    message_manager = get_message_manager()
    # Create a deep copy to avoid side effects
    messages = [msg.copy() for msg in message_manager.get_messages()]

    def dump_file_name(command_type: str, stem: str | None = None) -> str:
        dump_dir = "dumps"
        # Ensure the dumps directory exists
        os.makedirs(dump_dir, exist_ok=True)
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = (stem or "dump") + "_" + command_type + "_" + now
        extension = ".json" if command_type == "JSON" else ".txt"
        return dump_dir + "/" + stem + extension
    
    def write_dump_file(dump: str, command_type: str, stem: str | None = None):
        filename = dump_file_name(command_type, stem)
        with open(filename, "w") as f:
            f.write(dump)
    
    if command_type == "JSON":
        # Start with system prompt
        with open('prompts/system.txt', 'r') as f:
            system_content = f.read()
        clean_messages = [{"role": "System", "content": system_content}]
        
        # Add conversation messages
        for msg in messages:
            # Only include role and content keys to match build_prompt_chain format
            clean_msg = {"role": msg["role"], "content": msg["content"]}
            clean_messages.append(clean_msg)
            
        dump = json.dumps(clean_messages, indent=2)
        write_dump_file(dump, command_type, command_label)
        return dump
    elif command_type == "EXAMPLE":
        dump = format_messages_example(messages)
        write_dump_file(dump, command_type, command_label)
        return dump
    elif command_type == "TRAIN":
        return "```\nTraining data dump format (placeholder)\n```"
    elif command_type.startswith("-"):
        try:
            n = int(command_type[1:])
            if not n > 0:
                n = None
            dump = format_messages_example(messages, n)
            write_dump_file(dump, command_type, command_label)
            return dump
        except ValueError:
            pass
    return "Invalid dump type"

class ConversationLogger:
    """Class to handle logging of conversation messages to a file."""
    
    def __init__(self):
        """Initialize the logger and create the log file."""
        self.log_file = None
        self.log_path = None
        self.start_log()
    
    def start_log(self):
        """Create a new log file for the current session."""
        try:
            # Create logs directory structure
            logs_dir = "logs"
            os.makedirs(logs_dir, exist_ok=True)
            
            # Create date-specific subdirectory (MM-DD format)
            today = datetime.now().strftime("%m-%d")
            day_dir = os.path.join(logs_dir, today)
            os.makedirs(day_dir, exist_ok=True)
            
            # Create log filename with timestamp (HH-MM-SS format)
            timestamp = datetime.now().strftime("%H%M%S")
            log_filename = f"log-{timestamp}.txt"
            self.log_path = os.path.join(day_dir, log_filename)
            
            # Initialize the log file with an empty string
            with open(self.log_path, "w") as f:
                f.write("")
            
            print(f"DEBUG - Log file created: {self.log_path}")
            return self.log_path
        except Exception as e:
            print(f"ERROR - Failed to create log file: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None
    
    def log_message(self, message):
        """Append a single message to the log file."""
        if not self.log_path:
            print("ERROR - Cannot log message: No log file path")
            return
        
        try:
            content = message["content"]
            role = message["role"]
            
            with open(self.log_path, "a") as f:
                if role == USER_ROLE:
                    f.write(f"{content}\n\n")
                elif role == ASSISTANT_ROLE:
                    f.write(f"{ASSISTANT_ROLE}:\n{content}\n\n")
        except Exception as e:
            print(f"ERROR - Failed to log message: {str(e)}")
    
    def log_messages(self, messages, append=True):
        """Log multiple messages to the file."""
        if not self.log_path:
            print("ERROR - Cannot log messages: No log file path")
            return
        
        try:
            # Format messages in the same format as the "EXAMPLE" dump
            log_content = format_messages_example(messages)
            
            # Write to log file (append or overwrite)
            mode = "a" if append else "w"
            with open(self.log_path, mode) as f:
                f.write(log_content)
            
            print(f"DEBUG - Messages logged to: {self.log_path}")
        except Exception as e:
            print(f"ERROR - Failed to log messages: {str(e)}")
            import traceback
            print(traceback.format_exc())

# Create a global instance of the logger
conversation_logger = None

def get_logger():
    """Get or create the conversation logger instance."""
    global conversation_logger
    if conversation_logger is None:
        conversation_logger = ConversationLogger()
    return conversation_logger
