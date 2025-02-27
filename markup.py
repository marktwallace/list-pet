import xml.etree.ElementTree as ET
from collections import defaultdict

def parse_markup(text):
    """Parses XML-like markup and returns a structured dictionary."""
    result = defaultdict(list)
    
    # Wrap in a root element to ensure valid XML parsing
    wrapped_text = f"<root>{text}</root>"
    
    try:
        root = ET.fromstring(wrapped_text)
        
        for element in root:
            tag = element.tag.strip().lower()
            content = element.text.strip() if element.text else ""

            if tag == "action":
                # Handle nested SQL or display elements inside action
                action_data = defaultdict(list)
                for sub_element in element:
                    sub_tag = sub_element.tag.strip().lower()
                    sub_content = sub_element.text.strip() if sub_element.text else ""
                    
                    # Handle SQL attributes like <sql df1>
                    if sub_tag == "sql" and sub_element.attrib:
                        sub_content = {"query": sub_content, "attributes": sub_element.attrib}
                    
                    action_data[sub_tag].append(sub_content)

                result["actions"].append(dict(action_data))
            else:
                result[tag].append(content)

    except ET.ParseError as e:
        print("Error parsing markup:", e)
        return None

    return dict(result)

# Example markup
markup_text = """
  <reasoning>
    Normalize the title and artist, find the album if known. Generate SQL for the insert.
  </reasoning>
  <action>
    <sql>
      INSERT INTO songs (title, artist)
      VALUES ('Cardigan', 'Taylor Swift');
    </sql>
  </action>
  <display>
    Song added. Here is our list so far:
  </display>
  <action>
    <sql df="df1" >
      SELECT * FROM songs;
    </sql>
    <display df="df1"/>
  </action>
"""

# Parsing the markup
parsed_data = parse_markup(markup_text)

# Display parsed structure
import json
print(json.dumps(parsed_data, indent=2))
