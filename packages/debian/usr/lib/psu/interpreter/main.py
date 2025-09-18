import sys
import os
import re

# --- GLOBAL STATE FOR INTERPRETER ---
variables = {}  # Stores PSU variables (e.g., set user_name = "Alice";)
html_output_buffer = []  # Accumulates generated HTML lines
output_filename = "index.html"  # Default output filename

# A simple stack to keep track of the current HTML parent for nesting.
# E.g., ['html', 'head', 'body', 'div']
html_tag_stack = []

# --- HELPER FUNCTIONS FOR PARSING ---

def parse_attributes(attr_string):
    """
    Parses a string like 'attr1="value1", attr2="value2"' into a dictionary.
    Assumes attributes are simple key="value" or key=value pairs.
    """
    attributes = {}
    if not attr_string:
        return attributes

    # Regex to find key="value" or key=value (for numbers/booleans)
    # It's simplified and assumes no commas *within* values.
    matches = re.findall(r'(\w+)=(?:"([^"]*)"|([^"\s,]+))', attr_string)
    for key, val1, val2 in matches:
        attributes[key] = val1 if val1 is not None else val2 # Prioritize quoted string, otherwise non-quoted
    return attributes

def interpolate_variables(text):
    """Replaces ${variableName} in a string with actual variable values."""
    def replace_var(match):
        var_name = match.group(1)
        return str(variables.get(var_name, f"UNDEFINED_VAR_{var_name}"))
    return re.sub(r'\$\{(\w+)\}', replace_var, text)

# --- HTML GENERATION HELPERS ---

def get_html_indent():
    """Calculates HTML indentation based on current tag stack depth."""
    return "    " * len(html_tag_stack)

def append_html_line(html_content):
    """Appends an HTML line to the buffer with appropriate indentation."""
    html_output_buffer.append(f"{get_html_indent()}{html_content}")

# --- MAIN INTERPRETER LOGIC ---

def execute_psu_script(filepath):
    global output_filename, variables, html_output_buffer, html_tag_stack

    print(f"--- Starting PSU Interpreter for: {filepath} ---")

    # Reset global state for each run to ensure clean execution
    variables = {}
    html_output_buffer = []
    output_filename = "index.html" # Reset to default
    html_tag_stack = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: PSU script file not found at '{filepath}'")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading PSU script file: {e}")
        sys.exit(1)

    # --- CORE `psload` AND `psstart` CHECK ---
    if not lines or lines[0].strip() != 'psload':
        print(f"Error: .psu script '{filepath}' must start with 'psload' on the first line.")
        sys.exit(1)
    if len(lines) < 2 or lines[1].strip() != 'psstart':
        print(f"Error: .psu script '{filepath}' must have 'psstart' on the second line.")
        sys.exit(1)
    print("`psload` and `psstart` directives validated.")
    # --- END CORE `psload` AND `psstart` CHECK ---

    # --- Line-by-Line Processing with Indentation Tracking and Block Management ---
    # This simplified parser uses a stack to manage active blocks (like 'page', 'section', 'container').
    # Each item in block_stack is a tuple: (indent_level, 'command_type', {command_data})
    block_stack = []

    # State variables for conditional execution (if/else) and loops
    skip_current_block = False
    if_conditions_met_stack = [] # Tracks if conditions were met for parent 'if' blocks

    current_line_index = 2 # Start from the third line after psload/psstart
    while current_line_index < len(lines):
        line = lines[current_line_index]
        trimmed_line = line.strip()
        line_indent_spaces = len(line) - len(line.lstrip())

        # Skip comments and empty lines
        if trimmed_line.startswith('..') or not trimmed_line:
            current_line_index += 1
            continue

        # Adjust block stack based on indentation
        # Close blocks whose indentation level is less than or equal to current line's
        while block_stack and line_indent_spaces <= block_stack[-1][0]:
            closed_indent, closed_cmd_type, closed_cmd_data = block_stack.pop()

            # Handle conditional skipping (for if/else)
            if closed_cmd_type == 'if':
                if_conditions_met_stack.pop()
                if not if_conditions_met_stack: # Reset global skip if all 'if's are closed
                    skip_current_block = False
                else: # Inherit skip status from parent 'if'
                    skip_current_block = not if_conditions_met_stack[-1]

            # Close corresponding HTML tags
            if closed_cmd_type == 'page':
                append_html_line("    </body>") # Assuming body was opened by 'page'
                append_html_line("</html>")
            elif closed_cmd_type in ['section', 'container', 'list']:
                 append_html_line(f"</{closed_cmd_data['html_tag']}>")
                 if html_tag_stack and html_tag_stack[-1] == closed_cmd_data['html_tag']:
                     html_tag_stack.pop()
            elif closed_cmd_type == 'card':
                # Card closing needs to close the main card div
                append_html_line("</div>") # Closes <div class="psu-card ...">
                if html_tag_stack and html_tag_stack[-1] == 'div':
                     html_tag_stack.pop()
            elif closed_cmd_type in ['card_body', 'card_footer']:
                append_html_line(f"</div>") # Closes <div class="psu-card-body"> or <div class="psu-card-footer">
                if html_tag_stack and html_tag_stack[-1] == 'div':
                     html_tag_stack.pop()

        # Check if we should skip processing this line due to 'if' conditions
        if skip_current_block:
            current_line_index += 1
            continue

        # --- Parse and Interpret Command ---
        # Find the command and its arguments string
        command_match = re.match(r'(\w+)\s*(.*)', trimmed_line)
        if not command_match:
            print(f"Error: Malformed line {current_line_index + 1}: '{trimmed_line}'")
            sys.exit(1)

        command = command_match.group(1)
        arg_string = command_match.group(2).strip()

        # Check for colon at end for block commands
        trimmed_endswith_colon = False
        if arg_string.endswith(':'):
            trimmed_endswith_colon = True
            arg_string = arg_string.rstrip(':').strip()


        try:
            # Command: output_html
            if command == 'output_html':
                match = re.match(r'"([^"]+)"', arg_string)
                if match:
                    output_filename = match.group(1)
                else:
                    raise ValueError("`output_html` expects a quoted filename.")

            # Command: set
            elif command == 'set':
                match = re.match(r'(\w+)\s*=\s*(.+);', arg_string)
                if match:
                    var_name = match.group(1)
                    value_expr = match.group(2).strip()
                    if value_expr.startswith('"') and value_expr.endswith('"'):
                        variables[var_name] = value_expr.strip('"')
                    elif value_expr.lower() in ['true', 'false']:
                        variables[var_name] = (value_expr.lower() == 'true')
                    elif re.match(r'^-?\d+(\.\d+)?$', value_expr): # Number
                        variables[var_name] = float(value_expr) if '.' in value_expr else int(value_expr)
                    else: # Attempt to evaluate as expression (careful with security!)
                        try:
                            # Limited environment to prevent arbitrary code execution
                            safe_globals = {"__builtins__": None, "True": True, "False": False}
                            evaluated_value = eval(value_expr, safe_globals, variables)
                            variables[var_name] = evaluated_value
                        except (NameError, SyntaxError, TypeError):
                            print(f"Warning: Could not evaluate expression for '{var_name}': '{value_expr}'")
                            variables[var_name] = None
                else:
                    raise ValueError("Invalid `set` command syntax.")

            # Command: page (main document structure)
            elif command == 'page':
                match = re.match(r'"([^"]+)"\s*(.*)', arg_string)
                if match:
                    page_title = match.group(1)
                    attrs_str = match.group(2).strip()
                    page_attrs = parse_attributes(attrs_str)

                    append_html_line("<!DOCTYPE html>")
                    append_html_line("<html>")
                    html_tag_stack.append('html') # Push html tag to stack
                    append_html_line("<head>")
                    html_tag_stack.append('head') # Push head tag to stack
                    append_html_line(f"    <title>{interpolate_variables(page_title)}</title>")
                    if 'stylesheet' in page_attrs:
                        append_html_line(f'    <link rel="stylesheet" href="{page_attrs["stylesheet"]}">')
                    if 'script' in page_attrs:
                        append_html_line(f'    <script src="{page_attrs["script"]}"></script>')
                    if 'favicon' in page_attrs:
                        append_html_line(f'    <link rel="icon" href="{page_attrs["favicon"]}">')
                    append_html_line("</head>")
                    html_tag_stack.pop() # Pop head tag
                    append_html_line("<body>")
                    html_tag_stack.append('body') # Push body tag to stack
                    block_stack.append((line_indent_spaces, 'page', {}))
                else:
                    raise ValueError("Invalid `page` command syntax.")

            # Command: meta_info
            elif command == 'meta_info':
                attrs = parse_attributes(arg_string)
                attr_str = ' '.join([f'{k}="{interpolate_variables(v)}"' for k, v in attrs.items()])
                append_html_line(f"<meta {attr_str}>")

            # Command: section
            elif command == 'section':
                match = re.match(r'"([^"]+)"\s*(.*)', arg_string)
                if match:
                    section_id = match.group(1)
                    attrs_str = match.group(2).strip()
                    attrs = parse_attributes(attrs_str)
                    
                    # Handle 'full_width' specifically if it was a custom attribute
                    extra_class = ""
                    if 'full_width' in attrs and str(attrs['full_width']).lower() == 'true':
                        extra_class = " full-width-section" # Define this CSS class in your stylesheet

                    existing_class = attrs.get('class', '')
                    final_class = f"class=\"{existing_class}{extra_class}\"".strip() if existing_class or extra_class else ""

                    # Reconstruct attributes string without 'full_width' if it was a custom PSU attribute
                    filtered_attrs = {k: v for k, v in attrs.items() if k != 'full_width'}
                    attr_str_html = ' '.join([f'{k}="{interpolate_variables(v)}"' for k, v in filtered_attrs.items()])
                    
                    append_html_line(f"<section id=\"{interpolate_variables(section_id)}\" {final_class} {attr_str_html}>".strip())
                    html_tag_stack.append('section')
                    block_stack.append((line_indent_spaces, 'section', {'html_tag': 'section'}))
                else:
                    raise ValueError("Invalid `section` command syntax.")

            # Command: container
            elif command == 'container':
                attrs = parse_attributes(arg_string)
                attr_str_html = ' '.join([f'{k}="{interpolate_variables(v)}"' for k, v in attrs.items()])
                append_html_line(f"<div {attr_str_html}>")
                html_tag_stack.append('div')
                block_stack.append((line_indent_spaces, 'container', {'html_tag': 'div'}))

            # Command: heading
            elif command == 'heading':
                match = re.match(r'level=(\d+)\s*"([^"]+)"\s*(.*)', arg_string)
                if match:
                    level = int(match.group(1))
                    text_content = match.group(2)
                    attrs_str = match.group(3).strip()
                    attrs = parse_attributes(attrs_str)
                    attr_str_html = ' '.join([f'{k}="{interpolate_variables(v)}"' for k, v in attrs.items()])
                    if not (1 <= level <= 6):
                        raise ValueError("Heading level must be between 1 and 6.")
                    append_html_line(f"<h{level} {attr_str_html}>{interpolate_variables(text_content)}</h{level}>")
                else:
                    raise ValueError("Invalid `heading` command syntax.")

            # Command: paragraph
            elif command == 'paragraph':
                match = re.match(r'"([^"]+)"\s*(.*)', arg_string)
                if match:
                    text_content = match.group(1)
                    attrs_str = match.group(2).strip()
                    attrs = parse_attributes(attrs_str)
                    attr_str_html = ' '.join([f'{k}="{interpolate_variables(v)}"' for k, v in attrs.items()])
                    append_html_line(f"<p {attr_str_html}>{interpolate_variables(text_content)}</p>")
                else:
                    raise ValueError("Invalid `paragraph` command syntax.")

            # Command: image
            elif command == 'image':
                match = re.match(r'"([^"]+)"\s*(.*)', arg_string)
                if match:
                    src = match.group(1)
                    attrs_str = match.group(2).strip()
                    attrs = parse_attributes(attrs_str)
                    attr_str_html = ' '.join([f'{k}="{interpolate_variables(v)}"' for k, v in attrs.items()])
                    append_html_line(f'<img src="{interpolate_variables(src)}" {attr_str_html}>')
                else:
                    raise ValueError("Invalid `image` command syntax.")

            # Command: button
            elif command == 'button':
                match = re.match(r'"([^"]+)"\s*(.*)', arg_string)
                if match:
                    text_content = match.group(1)
                    attrs_str = match.group(2).strip()
                    attrs = parse_attributes(attrs_str)
                    attr_str_html = ' '.join([f'{k}="{interpolate_variables(v)}"' for k, v in attrs.items()])
                    append_html_line(f"<button {attr_str_html}>{interpolate_variables(text_content)}</button>")
                else:
                    raise ValueError("Invalid `button` command syntax.")

            # Command: link
            elif command == 'link':
                match = re.match(r'"([^"]+)"\s*"([^"]+)"\s*(.*)', arg_string)
                if match:
                    display_text = match.group(1)
                    href = match.group(2)
                    attrs_str = match.group(3).strip()
                    attrs = parse_attributes(attrs_str)
                    attr_str_html = ' '.join([f'{k}="{interpolate_variables(v)}"' for k, v in attrs.items()])
                    append_html_line(f'<a href="{interpolate_variables(href)}" {attr_str_html}>{interpolate_variables(display_text)}</a>')
                else:
                    raise ValueError("Invalid `link` command syntax.")

            # Command: list
            elif command == 'list':
                match = re.match(r'type="(ordered|unordered)"\s*(.*)', arg_string)
                if match:
                    list_type = match.group(1)
                    html_tag = 'ol' if list_type == 'ordered' else 'ul'
                    attrs_str = match.group(2).strip()
                    attrs = parse_attributes(attrs_str)
                    attr_str_html = ' '.join([f'{k}="{interpolate_variables(v)}"' for k, v in attrs.items()])
                    append_html_line(f"<{html_tag} {attr_str_html}>")
                    html_tag_stack.append(html_tag)
                    block_stack.append((line_indent_spaces, 'list', {'html_tag': html_tag}))
                else:
                    raise ValueError("Invalid `list` command syntax.")

            # Command: item (must be inside a list)
            elif command == 'item':
                if not block_stack or block_stack[-1][1] not in ['list']: # Must be directly in a list
                    raise ValueError("`item` command must be directly inside a `list` block.")
                
                match = re.match(r'"([^"]+)"\s*(.*)', arg_string)
                if match:
                    text_content = match.group(1)
                    attrs_str = match.group(2).strip()
                    attrs = parse_attributes(attrs_str)
                    attr_str_html = ' '.join([f'{k}="{interpolate_variables(v)}"' for k, v in attrs.items()])
                    append_html_line(f"<li {attr_str_html}>{interpolate_variables(text_content)}</li>")
                else:
                    raise ValueError("Invalid `item` command syntax.")

            # Command: card
            elif command == 'card':
                match = re.match(r'title="([^"]+)"\s*(.*)', arg_string)
                if match:
                    card_title_text = match.group(1)
                    attrs_str = match.group(2).strip()
                    attrs = parse_attributes(attrs_str)
                    attr_str_html = ' '.join([f'{k}="{interpolate_variables(v)}"' for k, v in attrs.items()])
                    
                    # Main card div
                    card_class = attrs.get('class', '')
                    append_html_line(f"<div class=\"psu-card {card_class}\" {attr_str_html.replace(f'class=\"{card_class}\"', '')}>".strip())
                    
                    # Card header
                    append_html_line(f"    <div class=\"psu-card-header\">")
                    append_html_line(f"        <h2>{interpolate_variables(card_title_text)}</h2>")
                    append_html_line(f"    </div>")

                    html_tag_stack.append('div') # For the main card div
                    block_stack.append((line_indent_spaces, 'card', {}))
                else:
                    raise ValueError("Invalid `card` command syntax.")

            # Command: card_body
            elif command == 'card_body':
                if not block_stack or block_stack[-1][1] not in ['card']:
                    raise ValueError("`card_body` must be directly inside a `card` block.")
                append_html_line(f"<div class=\"psu-card-body\">")
                html_tag_stack.append('div') # For card_body div
                block_stack.append((line_indent_spaces, 'card_body', {}))

            # Command: card_footer
            elif command == 'card_footer':
                if not block_stack or block_stack[-1][1] not in ['card']:
                    raise ValueError("`card_footer` must be directly inside a `card` block.")
                append_html_line(f"<div class=\"psu-card-footer\">")
                html_tag_stack.append('div') # For card_footer div
                block_stack.append((line_indent_spaces, 'card_footer', {}))

            # Command: if (simplified, only checks boolean variables or simple equality for now)
            elif command == 'if':
                condition_expr = arg_string
                # VERY SIMPLIFIED: Needs robust expression parsing for production
                condition_result = False
                if '==' in condition_expr:
                    left, right = [p.strip() for p in condition_expr.split('==', 1)]
                    left_val = variables.get(left)
                    right_val = right.strip('"').lower() if right.startswith('"') and right.endswith('"') else right.lower()
                    condition_result = (str(left_val).lower() == right_val)
                elif '!=' in condition_expr:
                    left, right = [p.strip() for p in condition_expr.split('!=', 1)]
                    left_val = variables.get(left)
                    right_val = right.strip('"').lower() if right.startswith('"') and right.endswith('"') else right.lower()
                    condition_result = (str(left_val).lower() != right_val)
                elif condition_expr in ['true', 'false']:
                    condition_result = (condition_expr.lower() == 'true')
                else: # Assume it's a boolean variable name
                    condition_result = bool(variables.get(condition_expr, False))

                # Push the condition result onto the stack
                if_conditions_met_stack.append(condition_result)
                # Set global skip based on current level and parent levels
                skip_current_block = not condition_result or any(not x for x in if_conditions_met_stack[:-1])
                block_stack.append((line_indent_spaces, 'if', {})) # Data can be empty, stack manages logic

            # Command: else (must follow an if, and has same indent level)
            elif command == 'else':
                if not block_stack or block_stack[-1][1] != 'if' or line_indent_spaces != block_stack[-1][0]:
                    raise ValueError("`else` command must immediately follow an `if` block at the same indentation level.")
                
                # Pop the last if condition from stack and re-evaluate for else
                prev_if_result = if_conditions_met_stack.pop()
                current_else_result = not prev_if_result # Else block executes if prev if was false
                if_conditions_met_stack.append(current_else_result)
                
                # Set global skip based on current level and parent levels
                skip_current_block = not current_else_result or any(not x for x in if_conditions_met_stack[:-1])
                # No need to push 'else' to block_stack, 'if' handles the block scope.

            # Command: loop (simplified to 'from X to Y')
            elif command == 'loop':
                # Looping within a line-by-line interpreter is complex for arbitrary commands.
                # For this simplified model, we'll mark this as a placeholder for a future AST-based
                # interpreter, and for now, only support very simple direct HTML generation loops.
                # A robust loop implementation would require parsing the loop's body and re-executing it.
                print(f"Warning: `loop` command on line {current_line_index + 1} is a placeholder.")
                print(f"       Full `loop` functionality requires an AST-based interpreter.")
                # For now, let's just create the block and skip its content.
                block_stack.append((line_indent_spaces, 'loop', {}))
                skip_current_block = True # Skip content for now, as not implemented


            # --- UNKNOWN COMMAND ---
            else:
                print(f"Warning: Unknown command or malformed syntax on line {current_line_index + 1}: '{trimmed_line}'")
                # For strictness, you could sys.exit(1) here.

        except ValueError as ve:
            print(f"Error on line {current_line_index + 1}: {ve}")
            sys.exit(1)
        except Exception as e:
            print(f"Unhandled error on line {current_line_index + 1}: {e}")
            # print(f"Current html_tag_stack: {html_tag_stack}") # Debugging
            # print(f"Current block_stack: {block_stack}") # Debugging
            sys.exit(1)

        current_line_index += 1

    # --- FINAL CLEANUP: Close any remaining open HTML tags ---
    while block_stack:
        closed_indent, closed_cmd_type, closed_cmd_data = block_stack.pop()
        if closed_cmd_type == 'page':
            # These are handled in the 'page' command's closing logic
            # append_html_line("    </body>")
            # append_html_line("</html>")
            pass
        elif closed_cmd_type in ['section', 'container', 'list']:
             append_html_line(f"</{closed_cmd_data['html_tag']}>")
             if html_tag_stack and html_tag_stack[-1] == closed_cmd_data['html_tag']:
                 html_tag_stack.pop()
        elif closed_cmd_type == 'card':
            append_html_line("</div>") # Closes <div class="psu-card ...">
            if html_tag_stack and html_tag_stack[-1] == 'div':
                 html_tag_stack.pop()
        elif closed_cmd_type in ['card_body', 'card_footer']:
            append_html_line(f"</div>") # Closes <div class="psu-card-body"> or <div class="psu-card-footer">
            if html_tag_stack and html_tag_stack[-1] == 'div':
                 html_tag_stack.pop()
        # For 'if' or 'loop' placeholders, no HTML tag to close here.

    # --- Write the accumulated HTML to the output file ---
    try:
        final_html_content = '\n'.join(html_output_buffer)
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(final_html_content)
        print(f"--- Successfully generated HTML file: {output_filename} ---")
    except Exception as e:
        print(f"Error writing HTML output file: {e}")
        sys.exit(1)

# --- How to run this interpreter from the command line ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python interpreter/main.py <path_to_psu_script.psu>")
        sys.exit(1)

    psu_file_path = sys.argv[1]
    if not psu_file_path.lower().endswith('.psu'):
        print("Error: Input file must have a .psu extension.")
        sys.exit(1)

    execute_psu_script(psu_file_path)
