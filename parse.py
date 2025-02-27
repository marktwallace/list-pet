import xml.etree.ElementTree as ET
import re
from collections import defaultdict

def parse_markup(text):
    """Parses XML-like markup into a structured dictionary with SQL, reasoning, and display sections."""
    result = defaultdict(list)
    
    # Wrap the text in a root element to ensure valid XML
    wrapped_text = f"<root>{text}</root>"
    
    try:
        root = ET.fromstring(wrapped_text)

        for element in root:
            tag = element.tag.strip().lower()
            content = element.text.strip() if element.text else ""

            if tag == "sql":
                # Extract dataframe name if provided (e.g., <sql df="df2">)
                sql_entry = {"query": content}
                if element.attrib:
                    sql_entry["df"] = element.attrib.get("df")
                result["sql"].append(sql_entry)

            elif tag == "display":
                # Detect inlined dataframe references (e.g., {{ df2 }})
                df_references = re.findall(r"\{\{\s*(\w+)\s*\}\}", content)
                result["display"].append({"text": content, "df_references": df_references})

            else:
                result[tag].append(content)

    except ET.ParseError as e:
        print("Error parsing markup:", e)
        print(text)
        return None

    return dict(result)

# Example markup
markup_text = """
  <reasoning>
    A year was provided. The table should be extended to accommodate the new data.
  </reasoning>
  <sql>
    ALTER TABLE songs
    ADD COLUMN release_year INTEGER;
  </sql>
  <sql>
    INSERT INTO songs (title, artist, release_year)
    VALUES ('Heroes', 'David Bowie', 1977);
  </sql>
  <sql df="df2">
    SELECT * FROM songs;
  </sql>
  <display>
    Added Heroes. Here is the current list:
    {{ df2 }}
  </display>
"""

# # Parse the markup
# parsed_data = parse_markup(markup_text)

# # Display parsed structure
# import json
# print(json.dumps(parsed_data, indent=2))

# Export the function
__all__ = ['parse_markup']
