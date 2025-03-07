import json
from datetime import datetime
import streamlit as st
from constants import ASSISTANT_ROLE, USER_ROLE

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
    # Create a deep copy to avoid side effects
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
