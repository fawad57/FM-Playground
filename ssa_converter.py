import re
from collections import defaultdict
import copy

class SSAInstruction:
    def __init__(self, target, expression):
        self.target = target
        self.expression = expression

    def __repr__(self):
        return f"{self.target} := {self.expression}"

class SSAConverter:
    def __init__(self):
        self.instructions = []
        self.current_versions = defaultdict(int)
        self.var_stack = defaultdict(list)
        self.seen_vars = set()
        self.cond_counter = 0
        self.array_versions = defaultdict(int)

    def get_versioned_var(self, var):
        if self.var_stack[var]:
            return self.var_stack[var][-1]
        versioned = f"{var}_0"
        if var not in self.seen_vars:
            self.seen_vars.add(var)
            self.var_stack[var].append(versioned)
        return versioned

    def new_version(self, var):
        self.seen_vars.add(var)
        self.current_versions[var] += 1
        versioned = f"{var}_{self.current_versions[var]}"
        self.var_stack[var].append(versioned)
        return versioned

    def new_cond_var(self):
        self.cond_counter += 1
        return f"cond_{self.cond_counter}"

    def _replace_vars(self, expr):
        # Handle array accesses (e.g., arr[j], arr[j+1])
        def replace_array_access(match):
            array_name = match.group(1)
            index_expr = self._replace_vars_in_expr(match.group(2))
            array_version = self.array_versions[array_name]
            return f"(select {array_name}_{array_version} {index_expr})"

        # Replace array accesses
        expr = re.sub(r'(\w+)\[([^\]]+)\]', replace_array_access, expr)

        # Replace variables in the rest of the expression
        return self._replace_vars_in_expr(expr)

    def _replace_vars_in_expr(self, expr):
        def replace_var(match):
            var = match.group(0)
            if var in ('if', 'else', 'while', 'for', 'assert', 'True', 'False'):
                return var
            self.seen_vars.add(var)
            return self.get_versioned_var(var)

        var_pattern = r'\b[a-zA-Z_]\w*\b'
        return re.sub(var_pattern, replace_var, expr)

    def convert(self, ast, unroll_depth=0):
        self.instructions = []
        self.current_versions.clear()
        self.var_stack.clear()
        self.seen_vars.clear()
        self.cond_counter = 0
        self.array_versions.clear()
        
        if unroll_depth > 0 and any(stmt.type in ["While", "For"] for stmt in ast.statements):
            self._convert_with_unrolling(ast, unroll_depth)
        else:
            self._convert_block(ast)
        
        return self.instructions

    def _convert_block(self, block, is_loop_body=False):
        for stmt in block.statements:
            if stmt.type == "Assign":
                expr = self._replace_vars(stmt.expression)
                target = self.new_version(stmt.variable)
                self.instructions.append(SSAInstruction(target, expr))

            elif stmt.type == "ArrayAssign":
                array_name = stmt.array
                index_expr = self._replace_vars_in_expr(stmt.index)
                expr = self._replace_vars(stmt.expression)
                # Increment array version
                prev_version = self.array_versions[array_name]
                self.array_versions[array_name] += 1
                new_version = self.array_versions[array_name]
                target = f"{array_name}_{new_version}"
                self.var_stack[array_name].append(target)
                self.instructions.append(SSAInstruction(target, f"(store {array_name}_{prev_version} {index_expr} {expr})"))

            elif stmt.type == "Assert":
                cond = self._replace_vars(stmt.condition)
                self.instructions.append(SSAInstruction("assert", cond))

            elif stmt.type == "If":
                cond = self._replace_vars(stmt.condition)
                cond_var = self.new_cond_var()
                self.instructions.append(SSAInstruction(cond_var, cond))
                
                before_if = copy.deepcopy(self.var_stack)
                before_array_versions = copy.deepcopy(self.array_versions)
                
                self._convert_block(stmt.true_branch)
                after_true = copy.deepcopy(self.var_stack)
                after_true_arrays = copy.deepcopy(self.array_versions)
                
                if stmt.false_branch:
                    self.var_stack = copy.deepcopy(before_if)
                    self.array_versions = copy.deepcopy(before_array_versions)
                    self._convert_block(stmt.false_branch)
                    after_false = copy.deepcopy(self.var_stack)
                    after_false_arrays = copy.deepcopy(self.array_versions)
                    
                    modified_vars = self._collect_modified_variables(stmt.true_branch) | self._collect_modified_variables(stmt.false_branch)
                    for var in modified_vars:
                        true_ver = after_true[var][-1] if var in after_true and after_true[var] else before_if[var][-1] if var in before_if and before_if[var] else f"{var}_0"
                        false_ver = after_false[var][-1] if var in after_false and after_false[var] else before_if[var][-1] if var in before_if and before_if[var] else f"{var}_0"
                        if true_ver != false_ver:
                            phi_var = self.new_version(var)
                            self.instructions.append(SSAInstruction(phi_var, f"φ({cond_var}, {true_ver}, {false_ver})"))
                            self.var_stack[var] = [phi_var]
                        else:
                            self.var_stack[var] = [true_ver]
                    
                    # Handle array phi nodes
                    array_vars = set(self.array_versions.keys())
                    for arr in array_vars:
                        true_ver = after_true_arrays.get(arr, 0)
                        false_ver = after_false_arrays.get(arr, 0)
                        if true_ver != false_ver:
                            self.array_versions[arr] = max(true_ver, false_ver) + 1
                            new_ver = self.array_versions[arr]
                            phi_var = f"{arr}_{new_ver}"
                            self.var_stack[arr] = [phi_var]
                            self.instructions.append(SSAInstruction(phi_var, f"φ({cond_var}, {arr}_{true_ver}, {arr}_{false_ver})"))
                        else:
                            self.array_versions[arr] = true_ver
                            self.var_stack[arr] = [f"{arr}_{true_ver}"]
                else:
                    modified_vars = self._collect_modified_variables(stmt.true_branch)
                    for var in modified_vars:
                        var_before = before_if[var][-1] if var in before_if and before_if[var] else f"{var}_0"
                        var_true = after_true[var][-1] if var in after_true and after_true[var] else var_before
                        phi_var = self.new_version(var)
                        self.instructions.append(SSAInstruction(phi_var, f"φ({cond_var}, {var_true}, {var_before})"))
                        self.var_stack[var] = [phi_var]
                    for var in self.seen_vars:
                        if var not in modified_vars:
                            if var in before_if and before_if[var]:
                                self.var_stack[var] = before_if[var]
                            else:
                                self.var_stack[var] = [f"{var}_0"]
                    # Restore array versions if no false branch
                    for arr in self.array_versions:
                        if arr not in after_true_arrays:
                            self.array_versions[arr] = before_array_versions.get(arr, 0)
                            self.var_stack[arr] = [f"{arr}_{self.array_versions[arr]}"]

            elif stmt.type == "While" and not is_loop_body:
                before_loop = copy.deepcopy(self.var_stack)
                before_array_versions = copy.deepcopy(self.array_versions)
                loop_vars = self._collect_variables_in_block(stmt.body) | self._extract_variables(stmt.condition)
                unconditional_mods = self._collect_unconditional_modifications(stmt.body)
                
                phi_nodes = {}
                for var in unconditional_mods:
                    if var in loop_vars:
                        entry_ver = before_loop[var][-1] if var in before_loop and before_loop[var] else f"{var}_0"
                        phi_var = self.new_version(var)
                        phi_nodes[var] = (phi_var, entry_ver)
                        self.instructions.append(SSAInstruction(phi_var, f"φ({entry_ver}, ?)"))

                cond = self._replace_vars(stmt.condition)
                self.instructions.append(SSAInstruction("while_cond", cond))
                
                self._convert_block(stmt.body, is_loop_body=True)
                after_body = copy.deepcopy(self.var_stack)
                after_body_arrays = copy.deepcopy(self.array_versions)
                
                for var, (phi_var, entry_ver) in phi_nodes.items():
                    back_edge = after_body[var][-1] if var in after_body and after_body[var] else entry_ver
                    for i, instr in enumerate(self.instructions):
                        if instr.target == phi_var and "?" in instr.expression:
                            self.instructions[i] = SSAInstruction(phi_var, f"φ({entry_ver}, {back_edge})")
                            break
                
                # Handle array phi nodes for loop
                array_vars = set(before_array_versions.keys())
                for arr in array_vars:
                    entry_ver = before_array_versions.get(arr, 0)
                    back_edge_ver = after_body_arrays.get(arr, entry_ver)
                    if entry_ver != back_edge_ver:
                        self.array_versions[arr] = back_edge_ver + 1
                        phi_var = f"{arr}_{self.array_versions[arr]}"
                        self.var_stack[arr] = [phi_var]
                        self.instructions.append(SSAInstruction(phi_var, f"φ(while_cond, {arr}_{entry_ver}, {arr}_{back_edge_ver})"))
                    else:
                        self.array_versions[arr] = entry_ver
                        self.var_stack[arr] = [f"{arr}_{entry_ver}"]
                
                for var in loop_vars:
                    if var not in phi_nodes:
                        self.var_stack[var] = before_loop[var] if var in before_loop and before_loop[var] else [f"{var}_0"]

            elif stmt.type == "For" and not is_loop_body:
                before_loop = copy.deepcopy(self.var_stack)
                before_array_versions = copy.deepcopy(self.array_versions)
                
                init_parts = stmt.init.split(":=")
                var = init_parts[0].strip()
                init_expr = self._replace_vars(init_parts[1].strip())
                init_var = self.new_version(var)
                self.instructions.append(SSAInstruction(init_var, init_expr))
                
                loop_vars = self._collect_variables_in_block(stmt.body) | self._extract_variables(stmt.condition) | self._extract_variables(stmt.update) | {var}
                phi_nodes = {}
                for loop_var in loop_vars:
                    if loop_var in self._collect_modified_variables(stmt.body) or loop_var == var:
                        entry_ver = init_var if loop_var == var else before_loop[loop_var][-1] if loop_var in before_loop and before_loop[loop_var] else f"{loop_var}_0"
                        phi_var = self.new_version(loop_var)
                        phi_nodes[loop_var] = (phi_var, entry_ver)
                        self.instructions.append(SSAInstruction(phi_var, f"φ({entry_ver}, ?)"))
                
                cond = self._replace_vars(stmt.condition)
                self.instructions.append(SSAInstruction("for_cond", cond))
                
                self._convert_block(stmt.body, is_loop_body=True)
                
                update_parts = stmt.update.split(":=")
                update_var = init_parts[0].strip()
                update_expr = self._replace_vars(update_parts[1].strip())
                update_var_new = self.new_version(update_var)
                self.instructions.append(SSAInstruction(update_var_new, update_expr))
                
                after_body = copy.deepcopy(self.var_stack)
                after_body_arrays = copy.deepcopy(self.array_versions)
                
                for loop_var, (phi_var, entry_ver) in phi_nodes.items():
                    back_edge = update_var_new if loop_var == var else after_body[loop_var][-1] if loop_var in after_body and after_body[loop_var] else entry_ver
                    for i, instr in enumerate(self.instructions):
                        if instr.target == phi_var and "?" in instr.expression:
                            self.instructions[i] = SSAInstruction(phi_var, f"φ({entry_ver}, {back_edge})")
                            break
                
                # Handle array phi nodes for loop
                array_vars = set(before_array_versions.keys())
                for arr in array_vars:
                    entry_ver = before_array_versions.get(arr, 0)
                    back_edge_ver = after_body_arrays.get(arr, entry_ver)
                    if entry_ver != back_edge_ver:
                        self.array_versions[arr] = back_edge_ver + 1
                        phi_var = f"{arr}_{self.array_versions[arr]}"
                        self.var_stack[arr] = [phi_var]
                        self.instructions.append(SSAInstruction(phi_var, f"φ(for_cond, {arr}_{entry_ver}, {arr}_{back_edge_ver})"))
                    else:
                        self.array_versions[arr] = entry_ver
                        self.var_stack[arr] = [f"{arr}_{entry_ver}"]
                
                for loop_var in loop_vars:
                    if loop_var not in phi_nodes:
                        self.var_stack[loop_var] = before_loop[loop_var] if loop_var in before_loop and before_loop[loop_var] else [f"{loop_var}_0"]

    def _convert_with_unrolling(self, ast, unroll_depth):
        for stmt in ast.statements:
            if stmt.type not in ["While", "For"]:
                self._convert_block(StmtBlock([stmt]))
            else:
                before_loop = copy.deepcopy(self.var_stack)
                before_array_versions = copy.deepcopy(self.array_versions)
                loop_vars = self._collect_variables_in_block(stmt.body) | self._extract_variables(stmt.condition)
                
                if stmt.type == "For":
                    init_parts = stmt.init.split(":=")
                    var = init_parts[0].strip()
                    init_expr = self._replace_vars(init_parts[1].strip())
                    init_var = self.new_version(var)
                    self.instructions.append(SSAInstruction(init_var, init_expr))
                    loop_vars |= {var}
                
                for var in loop_vars:
                    if var not in self.var_stack or not self.var_stack[var]:
                        self.var_stack[var].append(f"{var}_0")
                        self.seen_vars.add(var)
                
                # Unroll the loop
                for _ in range(unroll_depth):
                    cond = self._replace_vars(stmt.condition)
                    cond_var = self.new_cond_var()
                    self.instructions.append(SSAInstruction(cond_var, cond))
                    if any(s.type in ["While", "For"] for s in stmt.body.statements):
                        for body_stmt in stmt.body.statements:
                            if body_stmt.type in ["While", "For"]:
                                self._convert_with_unrolling(StmtBlock([body_stmt]), unroll_depth)
                            else:
                                self._convert_block(StmtBlock([body_stmt]))
                    else:
                        self._convert_block(stmt.body)
                    if stmt.type == "For":
                        update_parts = stmt.update.split(":=")
                        update_var = init_parts[0].strip()
                        update_expr = self._replace_vars(update_parts[1].strip())
                        update_var_new = self.new_version(update_var)
                        self.instructions.append(SSAInstruction(update_var_new, update_expr))
                
                after_loop = copy.deepcopy(self.var_stack)
                after_loop_arrays = copy.deepcopy(self.array_versions)
                
                # Handle array versions after unrolling
                array_vars = set(before_array_versions.keys())
                for arr in array_vars:
                    if arr in after_loop_arrays and after_loop_arrays[arr] != before_array_versions.get(arr, 0):
                        self.array_versions[arr] = after_loop_arrays[arr]
                        self.var_stack[arr] = [f"{arr}_{self.array_versions[arr]}"]
                    else:
                        self.array_versions[arr] = before_array_versions.get(arr, 0)
                        self.var_stack[arr] = [f"{arr}_{self.array_versions[arr]}"]
                
                for var in loop_vars:
                    if var not in self._collect_modified_variables(stmt.body) and var not in (init_parts[0].strip() if stmt.type == "For" else []):
                        self.var_stack[var] = before_loop[var] if var in before_loop and before_loop[var] else [f"{var}_0"]
                    elif var not in after_loop or not after_loop[var]:
                        self.var_stack[var] = before_loop[var] if var in before_loop and before_loop[var] else [f"{var}_0"]

    def _collect_variables_in_block(self, block):
        variables = set()
        for stmt in block.statements:
            if stmt.type == "Assign":
                variables.add(stmt.variable)
                variables.update(self._extract_variables(stmt.expression))
            elif stmt.type == "ArrayAssign":
                variables.add(stmt.array)
                variables.update(self._extract_variables(stmt.index))
                variables.update(self._extract_variables(stmt.expression))
            elif stmt.type == "Assert":
                variables.update(self._extract_variables(stmt.condition))
            elif stmt.type == "If":
                variables.update(self._extract_variables(stmt.condition))
                variables.update(self._collect_variables_in_block(stmt.true_branch))
                if stmt.false_branch:
                    variables.update(self._collect_variables_in_block(stmt.false_branch))
            elif stmt.type == "While":
                variables.update(self._extract_variables(stmt.condition))
                variables.update(self._collect_variables_in_block(stmt.body))
            elif stmt.type == "For":
                init_parts = stmt.init.split(":=")
                variables.add(init_parts[0].strip())
                variables.update(self._extract_variables(init_parts[1].strip()))
                variables.update(self._extract_variables(stmt.condition))
                variables.update(self._collect_variables_in_block(stmt.body))
                update_parts = stmt.update.split(":=")
                variables.update(self._extract_variables(update_parts[1].strip()))
        return variables

    def _collect_modified_variables(self, block):
        modified = set()
        for stmt in block.statements:
            if stmt.type == "Assign":
                modified.add(stmt.variable)
            elif stmt.type == "ArrayAssign":
                modified.add(stmt.array)  # Track array as modified
            elif stmt.type == "If":
                true_mod = self._collect_modified_variables(stmt.true_branch)
                false_mod = self._collect_modified_variables(stmt.false_branch) if stmt.false_branch else set()
                modified.update(true_mod | false_mod)
            elif stmt.type == "While" or stmt.type == "For":
                modified.update(self._collect_modified_variables(stmt.body))
        return modified

    def _collect_unconditional_modifications(self, block):
        modified = set()
        for stmt in block.statements:
            if stmt.type == "Assign":
                modified.add(stmt.variable)
            elif stmt.type == "ArrayAssign":
                modified.add(stmt.array)
            elif stmt.type == "If":
                true_mod = self._collect_unconditional_modifications(stmt.true_branch)
                false_mod = self._collect_unconditional_modifications(stmt.false_branch) if stmt.false_branch else set()
                modified.update(true_mod & false_mod)
            elif stmt.type == "While" or stmt.type == "For":
                modified.update(self._collect_unconditional_modifications(stmt.body))
        return modified

    def _extract_variables(self, expr):
        var_pattern = r'\b[a-zA-Z_]\w*\b'
        keywords = ('if', 'else', 'while', 'for', 'assert', 'True', 'False')
        vars = set(re.findall(var_pattern, expr))
        return {v for v in vars if v not in keywords}

class StmtBlock:
    def __init__(self, statements):
        self.statements = statements