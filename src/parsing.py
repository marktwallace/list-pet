import re
import os

SQL_REGEX = r"^\s*(?:" + \
    r"SELECT\s+(?:\w+|\*)|" + \
    r"CREATE\s+(?:TABLE|DATABASE|VIEW|INDEX)|" + \
    r"DROP\s+(?:TABLE|DATABASE|VIEW|INDEX)|" + \
    r"ALTER\s+(?:TABLE|DATABASE|VIEW)|" + \
    r"INSERT\s+INTO|" + \
    r"DELETE\s+FROM|" + \
    r"UPDATE\s+\w+|" + \
    r"SHOW\s+(?:TABLES|DATABASES|COLUMNS)|" + \
    r"DESCRIBE\s+\w+" + \
    r")\s*.*"

def get_elements(content):
    result = {}        
    # Updated pattern to capture tag attributes
    pattern = r'<(\w+)(\s+[^>]*)?>(?s)(.*?)</\1>'
    matches = re.finditer(pattern, content, re.DOTALL)
    for match in matches:
        tag_name = match.group(1)
        attributes_str = match.group(2) or ""
        tag_content = match.group(3).strip()
        content = content.replace(match.group(0), "")
        
        # Parse attributes into a dictionary
        attributes = {}
        if attributes_str:
            attr_pattern = r'(\w+)=["\']([^"\']*)["\']'
            attr_matches = re.finditer(attr_pattern, attributes_str)
            for attr_match in attr_matches:
                attr_name = attr_match.group(1)
                attr_value = attr_match.group(2)
                attributes[attr_name] = attr_value
        
        # Store both content and attributes
        if tag_name not in result:
            result[tag_name] = []
        result[tag_name].append({"content": tag_content, "attributes": attributes})
        
    result["markdown"] = content
    return result

def main():
    """Test function to read and parse messages from example.txt"""
    with open(os.path.join(os.path.dirname(__file__), "../prompts/example.txt"), "r") as f:
        content = f.read()
    
    # Split content into messages
    # Pattern to match User: and Assistant: prefixes with content
    message_pattern = r"(?:User|Assistant):\s*([\s\S]*?)(?=(?:User|Assistant):|$)"
    messages = re.findall(message_pattern, content)
    
    # Track stats
    total_messages = len(messages)
    successful_parses = 0
    
    # Parse each message
    for i, message in enumerate(messages):
        if not message.strip():
            continue
            
        try:
            elements = get_elements(message.strip())
            successful_parses += 1
            
            # Print some info about what was parsed
            tags = [f"{tag}({len(items)})" for tag, items in elements.items() if tag != "markdown"]
            if tags:
                print(f"Message {i+1}: Found {', '.join(tags)}")
            else:
                print(f"Message {i+1}: No tags found, only markdown")
                
        except Exception as e:
            print(f"Failed to parse message {i+1}: {e}")
    
    # Print summary
    print(f"\nSummary: Successfully parsed {successful_parses}/{total_messages} messages")
    return successful_parses == total_messages

if __name__ == "__main__":
    success = main()
    print(f"Test {'passed' if success else 'failed'}")
