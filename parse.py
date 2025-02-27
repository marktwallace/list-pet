import json
import sys

def parse_text_file(filename):
    """Parses a structured text file into a list of conversation turns."""
    conversations = []
    current_role = None
    current_text = []

    with open(filename, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line:
                continue  # Skip empty lines
            
            # Detect role headers
            if line.endswith(":") and line in {"SYSTEM:", "USER:", "ASSISTANT:"}:
                if current_role and current_text:
                    # Save previous role and text
                    conversations.append({"role": current_role.lower(), "content": "\n".join(current_text)})
                current_role = line[:-1]  # Remove the colon
                current_text = []
            else:
                current_text.append(line)

        # Save last entry
        if current_role and current_text:
            conversations.append({"role": current_role.lower(), "content": "\n".join(current_text)})

    return conversations

def convert_to_jsonl(conversations, output_filename):
    """Writes the parsed conversation list into a JSONL file."""
    with open(output_filename, 'w', encoding='utf-8') as jsonl_file:
        for conv in conversations:
            jsonl_file.write(json.dumps(conv, ensure_ascii=False) + '\n')

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse.py <basename>")
        sys.exit(1)
        
    base_name = sys.argv[1]
    input_filename = f"{base_name}.txt"
    output_filename = f"{base_name}.jsonl"

    conversations = parse_text_file(input_filename)
    convert_to_jsonl(conversations, output_filename)

    print(f"Converted {len(conversations)} entries to {output_filename}")
