import re

def parse_markup(text: str) -> dict:
    """Parse the AI response into structured components using regex parsing."""
    
    blocks = ["reasoning", "sql", "plot", "map", "display"]
    components = {block: [] for block in blocks}
    
    current_tag = None
    current_content = []
    in_plot_tag = False
    plot_lines = []
    in_map_tag = False
    map_lines = []

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
            
        # Handle multiline plot tags
        if line.startswith('<plot'):
            in_plot_tag = True
            plot_lines = [line]
            continue
        elif in_plot_tag:
            plot_lines.append(line)
            if line.endswith('/>'):
                # Process complete plot tag
                in_plot_tag = False
                full_plot_tag = ' '.join(plot_lines)
                
                # Parse the complete plot tag
                plot_match = re.match(r'<plot(.*?)>', full_plot_tag)
                if plot_match:
                    attrs = plot_match.group(1).strip()
                    plot_attrs = {}
                    # Split on spaces, but respect quoted values
                    attr_pattern = r'(\w+)="([^"]*)"'
                    for attr_match in re.finditer(attr_pattern, attrs):
                        key, value = attr_match.groups()
                        if key == 'hover_data':
                            # Convert comma-separated hover columns to list
                            plot_attrs[key] = [col.strip() for col in value.split(',')]
                        else:
                            plot_attrs[key] = value
                    components['plot'].append(plot_attrs)
            continue
            
        # Handle multiline map tags
        if line.startswith('<map'):
            in_map_tag = True
            map_lines = [line]
            continue
        elif in_map_tag:
            map_lines.append(line)
            if line.endswith('/>'):
                # Process complete map tag
                in_map_tag = False
                full_map_tag = ' '.join(map_lines)
                
                # Parse the complete map tag
                map_match = re.match(r'<map(.*?)>', full_map_tag)
                if map_match:
                    attrs = map_match.group(1).strip()
                    map_attrs = {}
                    # Split on spaces, but respect quoted values
                    attr_pattern = r'(\w+)="([^"]*)"'
                    for attr_match in re.finditer(attr_pattern, attrs):
                        key, value = attr_match.groups()
                        if key == 'hover_data':
                            # Convert comma-separated hover columns to list
                            map_attrs[key] = [col.strip() for col in value.split(',')]
                        else:
                            map_attrs[key] = value
                    components['map'].append(map_attrs)
            continue
            
        # Handle other tags
        opening_match = re.match(r'<(\w+)>', line)
        closing_tag = next((f"</{block}>" for block in blocks if line == f"</{block}>"), None)
        
        if opening_match:
            block_type = opening_match.group(1)
            if block_type in blocks and block_type not in ['plot', 'map']:
                current_tag = block_type
                current_content = []
                
        elif closing_tag:
            block_type = closing_tag[2:-1]  # Remove </> from tag
            if current_content and block_type not in ["plot", "map"]:  # Skip plot and map closing tags
                components[block_type].append(
                    {"query" if block_type == "sql" else "text": '\n'.join(current_content).strip()}
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

