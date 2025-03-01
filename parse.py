import xml.etree.ElementTree as ET
import re
from collections import defaultdict

def parse_markup(text: str) -> dict:
    """Parse the AI response into components (reasoning, sql, display)"""
    components = {
        "reasoning": [],
        "sql": [],
        "display": []
    }
    
    current_tag = None
    current_content = []
    
    for line in text.split('\n'):
        line = line.strip()
        
        # Check for opening tags
        if line.startswith('<reasoning>'):
            current_tag = 'reasoning'
            current_content = []
        elif line.startswith('<sql>'):
            current_tag = 'sql'
            current_content = []
            sql_attrs = {}  # For any SQL attributes
        elif line.startswith('<display>'):
            current_tag = 'display'
            current_content = []
            
        # Check for closing tags
        elif line.startswith('</reasoning>'):
            if current_content:
                components['reasoning'].append({
                    'text': '\n'.join(current_content).strip()
                })
            current_tag = None
        elif line.startswith('</sql>'):
            if current_content:
                components['sql'].append({
                    'query': '\n'.join(current_content).strip(),
                    **sql_attrs
                })
            current_tag = None
        elif line.startswith('</display>'):
            if current_content:
                components['display'].append({
                    'text': '\n'.join(current_content).strip()
                })
            current_tag = None
            
        # Collect content
        elif current_tag:
            # Special handling for SQL df attribute
            if current_tag == 'sql' and 'df=' in line:
                df_name = line.split('df=')[1].strip('"')
                sql_attrs['df'] = df_name
            else:
                current_content.append(line)
    
    return components

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
