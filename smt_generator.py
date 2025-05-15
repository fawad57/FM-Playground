import re
from collections import defaultdict

class SMTGenerator:
    def __init__(self):
        self.declarations = []
        self.assertions = []
        self.array_versions = defaultdict(list)
        self.variables = set()
        self.array_counter = defaultdict(int)
        self.initial_values = {}
        self.has_arrays = False
        self.var_versions = defaultdict(list)

    def generate_smt(self, ssa_instructions, mode="verification", ssa_instructions2=None):
        self.declarations = []
        self.assertions = []
        self.array_versions = defaultdict(list)
        self.var_versions = defaultdict(list)
        self.variables = set()
        self.array_counter = defaultdict(int)
        self.initial_values = {}
        self.has_arrays = False

        if mode == "verification":
            self._process_ssa(ssa_instructions, prefix="")
            if self.has_arrays:
                self._add_sorted_property()
        elif mode == "comparison":
            if not ssa_instructions2:
                raise ValueError("Comparison mode requires two sets of SSA instructions")
            self._process_ssa(ssa_instructions, prefix="_1")
            self._process_ssa(ssa_instructions2, prefix="_2")
            self._add_equivalence_property()
        else:
            raise ValueError(f"Unknown mode: {mode}")

        smt_code = ["(set-logic QF_AUFLIA)"]
        smt_code.extend(sorted(set(self.declarations)))
        for var, value in self.initial_values.items():
            smt_code.append(f"(assert (= {var} {value}))")
        smt_code.extend(self.assertions)
        smt_code.append("(check-sat)")
        smt_code.append("(get-model)")
        smt_code.append("(exit)")
        return "\n".join(smt_code)

    def _process_ssa(self, ssa_instructions, prefix=""):
        for instr in ssa_instructions:
            if "arr_" in instr.target or "arr_" in instr.expression:
                self.has_arrays = True
                break

        if self.has_arrays:
            current_array = f"arr_0{prefix}"
            self.declarations.append(f"(declare-fun {current_array} () (Array Int Int))")
            self.array_versions["arr"].append(current_array)

        for i, instr in enumerate(ssa_instructions):
            target = f"{instr.target}{prefix}"
            expr = instr.expression

            if target not in self.variables and not target.startswith("arr_") and target != "assert":
                self.variables.add(target)
                self.declarations.append(f"(declare-fun {target} () Int)")
                base_var = instr.target.split('_')[0]
                if base_var not in ("cond", "while", "for", "assert"):
                    self.var_versions[base_var].append(target)

            if "φ" in expr:
                self._handle_phi_node(target, expr, prefix)
            elif target.startswith("arr_"):
                self._handle_array_assignment(target, expr, prefix)
            elif target == "assert":
                smt_expr = self._translate_expression(expr, prefix)
                match = re.match(r'^\s*(\w+)\s*(==|=)\s*(\d+|\w+)\s*$', expr)
                if match:
                    left, _, right = match.groups()
                    left = f"{left}{prefix}"
                    smt_expr = f"(= {left} {right})"
                else:
                    smt_expr = smt_expr.replace("==", "=")
                    smt_expr = smt_expr.strip()
                    if not smt_expr.startswith("("):
                        smt_expr = f"({smt_expr})"
                self.assertions.append(f"(assert {smt_expr})")
            elif target in ("while_cond", "for_cond") or target.startswith("cond_"):
                self.assertions.append(f"(assert (= {target} {self._translate_expression(expr, prefix)}))")
            else:
                smt_expr = self._translate_expression(expr, prefix)
                if re.match(r'^\w+_1\s*:=\s*.+$', f"{target} := {expr}") and i == 0:
                    self.initial_values[target] = smt_expr
                else:
                    self.assertions.append(f"(assert (= {target} {smt_expr}))")

    def _handle_phi_node(self, target, expr, prefix):
        match = re.match(r'φ\(([^,]+),\s*([^,]+),\s*([^)]+)\)', expr)
        if not match:
            raise ValueError(f"Invalid phi node: {expr}")
        cond = f"{match.group(1)}{prefix}"
        val1 = f"{match.group(2)}{prefix}"
        val2 = f"{match.group(3)}{prefix}"
        self.variables.add(target)
        self.declarations.append(f"(declare-fun {target} () Int)")
        self.assertions.append(f"(assert (= {target} (ite {cond} {val1} {val2})))")

    def _handle_array_assignment(self, target, expr, prefix):
        self.array_counter["arr"] += 1
        new_array = target
        self.declarations.append(f"(declare-fun {new_array} () (Array Int Int))")
        self.array_versions["arr"].append(new_array)
        smt_expr = self._translate_expression(expr, prefix)
        self.assertions.append(f"(assert (= {new_array} {smt_expr}))")

    def _translate_expression(self, expr, prefix):
        def replace_var(match):
            var = match.group(0)
            if var in ('if', 'else', 'while', 'for', 'assert', 'True', 'False', 'select', 'store'):
                return var
            return f"{var}{prefix}"

        expr = re.sub(r'\b[a-zA-Z_]\w*\b', replace_var, expr)
        expr = expr.replace(":=", "=")
        expr = expr.replace("&&", "and")
        expr = expr.replace("||", "or")
        expr = expr.replace("!", "not")
        expr = re.sub(r'(\w+)\s*\+\s*(\d+|\w+)', r'(+ \1 \2)', expr)
        expr = re.sub(r'(\w+)\s*-\s*(\w+|\d+)', r'(- \1 \2)', expr)
        expr = re.sub(r'(\w+)\s*>\s*(\w+|\d+|\(.+?\))', r'(> \1 \2)', expr)
        expr = re.sub(r'(\w+)\s*<\s*(\w+|\d+|\(.+?\))', r'(< \1 \2)', expr)
        return expr

    def _add_sorted_property(self):
        final_array = self.array_versions["arr"][-1]
        n_var = "n_1"
        if n_var not in self.variables:
            self.declarations.append(f"(declare-fun {n_var} () Int)")
            self.variables.add(n_var)
        self.declarations.append("(declare-fun k () Int)")
        self.assertions.append(
            f"(assert (forall ((k Int)) (=> (and (<= 0 k) (< k (- {n_var} 1))) (<= (select {final_array} k) (select {final_array} (+ k 1))))))"
        )

    def _add_equivalence_property(self):
        # Compare arrays if they exist
        if self.has_arrays:
            arr_versions_1 = [v for v in self.array_versions["arr"] if v.endswith("_1")]
            arr_versions_2 = [v for v in self.array_versions["arr"] if v.endswith("_2")]
            if arr_versions_1 and arr_versions_2:
                arr1 = arr_versions_1[-1]
                arr2 = arr_versions_2[-1]
                self.assertions.append(f"(assert (= arr_0_1 arr_0_2))")
                self.assertions.append(f"(assert (= {arr1} {arr2}))")
            else:
                raise ValueError("Array versions missing in one of the programs")

        # Compare scalar variables
        compared_vars = set()
        for var in self.var_versions:
            versions_1 = [v for v in self.var_versions[var] if v.endswith("_1")]
            versions_2 = [v for v in self.var_versions[var] if v.endswith("_2")]
            if versions_1 and versions_2:
                var1 = versions_1[-1]
                var2 = versions_2[-1]
                self.assertions.append(f"(assert (= {var1} {var2}))")
                compared_vars.add(var)
            elif versions_1:
                var1 = versions_1[-1]
                self.declarations.append(f"(declare-fun {var}_0_2 () Int)")
                self.assertions.append(f"(assert (= {var}_0_2 0))")
                self.assertions.append(f"(assert (= {var1} {var}_0_2))")
                compared_vars.add(var)
            elif versions_2:
                var2 = versions_2[-1]
                self.declarations.append(f"(declare-fun {var}_0_1 () Int)")
                self.assertions.append(f"(assert (= {var}_0_1 0))")
                self.assertions.append(f"(assert (= {var}_0_1 {var2}))")
                compared_vars.add(var)

        if not compared_vars and not self.has_arrays:
            raise ValueError("No variables to compare between programs")