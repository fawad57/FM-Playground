import os
import re
import graphviz
import uuid

class Node:
    def __init__(self, node_type, **kwargs):
        self.type = node_type
        self.__dict__.update(kwargs)

    def __repr__(self):
        return f"{self.type}({{ {', '.join(f'{k}: {v}' for k, v in self.__dict__.items() if k != 'type')} }})"

    def to_dict(self):
        """Convert the node to a dictionary for JSON serialization."""
        result = {"type": self.type}
        for key, value in self.__dict__.items():
            if key != "type":
                if isinstance(value, Node):
                    result[key] = value.to_dict()
                elif isinstance(value, list):
                    result[key] = [item.to_dict() if isinstance(item, Node) else item for item in value]
                else:
                    result[key] = value
        return result

class Parser:
    def __init__(self):
        self.lines = []
        self.index = 0

    def _preprocess_lines(self, code):
        """Preprocess the code to handle multi-line constructs and else clauses."""
        raw_lines = [line.strip() for line in code.split('\n') if line.strip()]
        processed_lines = []
        i = 0
        while i < len(raw_lines):
            line = raw_lines[i]
            # Handle else clauses
            if '}' in line and 'else' in line:
                match = re.search(r'(.*?)}\s*(else\s*\{?)', line)
                if match:
                    before = match.group(1).strip()
                    closing = '}'
                    after = match.group(2).strip()
                    if before:
                        processed_lines.append(before)
                    processed_lines.append(closing)
                    processed_lines.append(after)
                    i += 1
                    continue
            # Handle block start (if, while, for)
            if re.match(r"(if|while|for)\s*\(.+\)\s*\{", line):
                processed_lines.append(line)
                # Collect the block content
                block_lines = []
                brace_count = 1
                i += 1
                while i < len(raw_lines) and brace_count > 0:
                    block_line = raw_lines[i]
                    brace_count += block_line.count('{') - block_line.count('}')
                    block_lines.append(block_line)
                    i += 1
                # Add block lines individually
                processed_lines.extend(block_lines)
                continue
            # Handle regular statements
            processed_lines.append(line)
            i += 1
        return processed_lines

    def parse(self):
        return self.parse_block()

    def parse_block(self):
        block = []
        while self.index < len(self.lines):
            line = self.lines[self.index].strip()

            if not line:
                self.index += 1
                continue
            if line.startswith("}"):
                self.index += 1
                break
            elif line.startswith("if"):
                block.append(self.parse_if())
            elif line.startswith("while"):
                block.append(self.parse_while())
            elif line.startswith("for"):
                block.append(self.parse_for())
            else:
                stmt = self.parse_statement()
                if stmt:
                    block.append(stmt)
                else:
                    self.index += 1  # Skip unrecognized lines
        return Node("Block", statements=block)

    def parse_if(self):
        line = self.lines[self.index]
        match = re.match(r"if\s*\((.*)\)\s*\{", line)
        if not match:
            raise ValueError(f"Invalid if statement at line {self.index + 1}: {line}")
        condition = match.group(1).strip()
        self.index += 1
        true_branch = self.parse_block()

        false_branch = None
        if self.index < len(self.lines):
            next_line = self.lines[self.index].strip()
            if next_line.startswith("else"):
                if re.match(r"else\s*\{", next_line):
                    self.index += 1
                elif next_line == "else":
                    self.index += 1
                    if self.index < len(self.lines) and self.lines[self.index].startswith("{"):
                        self.index += 1
                false_branch = self.parse_block()

        return Node("If", condition=condition, true_branch=true_branch, false_branch=false_branch)

    def parse_while(self):
        line = self.lines[self.index]
        match = re.match(r"while\s*\((.*)\)\s*\{", line)
        if not match:
            raise ValueError(f"Invalid while statement at line {self.index + 1}: {line}")
        condition = match.group(1).strip()
        self.index += 1
        body = self.parse_block()
        return Node("While", condition=condition, body=body)

    def parse_for(self):
        line = self.lines[self.index]
        match = re.match(r"for\s*\(\s*(.+?)\s*;\s*(.+?)\s*;\s*(.+?)\s*\)\s*\{", line)
        if not match:
            raise ValueError(f"Invalid for statement at line {self.index + 1}: {line}")
        init, cond, update = match.groups()
        self.index += 1
        body = self.parse_block()
        return Node("For", init=init.strip(), condition=cond.strip(), update=update.strip(), body=body)

    def parse_statement(self):
        line = self.lines[self.index]
        self.index += 1
        if line.startswith("assert"):
            match = re.match(r"assert\s*\((.*)\);?", line)
            if not match:
                raise ValueError(f"Invalid assert statement at line {self.index}: {line}")
            condition = match.group(1).strip()
            if 'forall' in condition:
                raise ValueError("Forall assertions are not supported. Use a loop-based assertion instead.")
            return Node("Assert", condition=condition)
        elif re.match(r"[\w\[\]]+\s*:=\s*.+;", line):
            match = re.match(r"([\w\[\]]+)\s*:=\s*(.+);", line)
            if not match:
                raise ValueError(f"Invalid assignment statement at line {self.index}: {line}")
            variable = match.group(1).strip()
            expression = match.group(2).strip()
            if '[' in variable:
                array_match = re.match(r"(\w+)\[(.+)\]", variable)
                if not array_match:
                    raise ValueError(f"Invalid array assignment at line {self.index}: {variable}")
                array_name, index = array_match.groups()
                return Node("ArrayAssign", array=array_name, index=index.strip(), expression=expression)
            return Node("Assign", variable=variable, expression=expression)
        return None

    def generate_dot(self, ast):
        dot = graphviz.Digraph(format='png')

        def add_node(node, parent=None):
            node_name = str(id(node))
            label = f"{node.type}"

            if node.type == "If":
                label += f"\ncond: {node.condition}"
            elif node.type == "While":
                label += f"\ncond: {node.condition}"
            elif node.type == "For":
                label += f"\ninit: {node.init}\ncond: {node.condition}\nupdate: {node.update}"
            elif node.type == "Assert":
                label += f"\ncond: {node.condition}"
            elif node.type == "Assign":
                label += f"\n{node.variable} := {node.expression}"
            elif node.type == "ArrayAssign":
                label += f"\n{node.array}[{node.index}] := {node.expression}"

            dot.node(node_name, label=label)

            if parent:
                dot.edge(parent, node_name)

            if hasattr(node, 'true_branch') and node.true_branch:
                add_node(node.true_branch, node_name)
            if hasattr(node, 'false_branch') and node.false_branch:
                add_node(node.false_branch, node_name)
            if hasattr(node, 'body') and node.body:
                add_node(node.body, node_name)
            if hasattr(node, 'statements'):
                for stmt in node.statements:
                    add_node(stmt, node_name)

        add_node(ast)
        return dot

    def save_ast_graph(self, ast, output_path=None):
        """Save the AST graph as a PNG and return the file path."""
        dot = self.generate_dot(ast)
        if output_path is None:
            output_path = f"static/ast_{uuid.uuid4().hex}"
        dot.render(filename=output_path, format='png', cleanup=True)
        return f"{output_path}.png"

    def parse_program(self, code):
        """
        Parse the input code and generate an AST and DOT file.
        Returns a tuple (AST dict, PNG file path, AST Node) or an error message.
        """
        try:
            self.__init__()  # Reinitialize parser state
            self.lines = self._preprocess_lines(code)
            ast = self.parse()
            png_path = self.save_ast_graph(ast)
            return ast.to_dict(), png_path, ast
        except Exception as e:
            return f"Parsing error: {str(e)}"