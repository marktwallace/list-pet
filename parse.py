import xml.etree.ElementTree as ET
import re
from collections import defaultdict

def parse_markup(text: str) -> dict:
    """Parse the AI response into structured components (reasoning, sql, plot, display)."""
    
    blocks = ["reasoning", "sql", "plot", "display"]
    components = {block: [] for block in blocks}
    
    current_tag = None
    current_content = []

    for line in text.split('\n'):
        line = line.strip()

        # Check for opening and closing tags dynamically
        matched_block = next((block for block in blocks if line == f"<{block}>" or line == f"</{block}>"), None)

        if matched_block:
            if line == f"<{matched_block}>":
                current_tag = matched_block
                current_content = []
            elif line == f"</{matched_block}>":
                if current_content:
                    if matched_block == "plot":
                        # Parse plot attributes into a dictionary
                        plot_attrs = {}
                        for attr_line in current_content:
                            if ':' in attr_line:
                                key, value = attr_line.split(':', 1)
                                plot_attrs[key.strip()] = value.strip()
                        components[matched_block].append(plot_attrs)
                    else:
                        components[matched_block].append(
                            {"query" if matched_block == "sql" else "text": '\n'.join(current_content).strip()}
                        )
                current_tag = None
        elif current_tag:
            current_content.append(line)

    return components

# Export function
__all__ = ['parse_markup']

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

# Parse the markup
#parsed_data = parse_markup(markup_text)

# Display parsed structure
#import json
#print(json.dumps(parsed_data, indent=2))

