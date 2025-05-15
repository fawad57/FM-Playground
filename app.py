from flask import Flask, request, render_template
import logging
import json
import subprocess
import re
from parser import Parser, Node
from ssa_converter import SSAConverter
from smt_generator import SMTGenerator

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def run_z3(smt_code):
    try:
        with open("output.smt2", "w") as f:
            f.write(smt_code)
        result = subprocess.run(["C:\\z3-4.15.0-x64-win\\bin\\z3.exe", "output.smt2"], capture_output=True, text=True, timeout=10)
        output = result.stdout.strip()
        
        model = []
        status = "unknown"
        
        for line in output.split('\n'):
            line = line.strip()
            if line == "sat":
                status = "sat"
            elif line == "unsat":
                status = "unsat"
            elif line.startswith("(define-fun"):
                match = re.match(r'\(define-fun (\w+) \(\) (Int|Bool) (.+)\)', line)
                if match:
                    var, _, value = match.groups()
                    if value in ("true", "false"):
                        value = value.capitalize()
                    model.append(f"{var} = {value}")
            elif not line.startswith("(error"):
                model.append(line)
        
        if status == "sat" and not model:
            model = ["No model available due to errors."]
        elif status == "unsat":
            model = ["No counterexamples found (program is correct)."]
        elif status == "unknown":
            model = [output if output else "Verification inconclusive due to errors."]
        
        return status, model
    except subprocess.TimeoutExpired:
        return "error", ["Z3 timed out"]
    except FileNotFoundError:
        return "error", ["Z3 not found. Please ensure Z3 is installed or specify its path in app.py."]
    except Exception as e:
        return "error", [f"Z3 error: {str(e)}"]

def generate_unrolled_code(ast, unroll_depth):
    """Generate unrolled code from AST for display in the Parse tab."""
    def unroll_block(block, depth, indent=0):
        code = []
        for stmt in block.statements:
            if stmt.type == "Assign":
                code.append("  " * indent + f"{stmt.variable} := {stmt.expression};")
            elif stmt.type == "ArrayAssign":
                code.append("  " * indent + f"{stmt.array}[{stmt.index}] := {stmt.expression};")
            elif stmt.type == "Assert":
                code.append("  " * indent + f"assert({stmt.condition});")
            elif stmt.type == "If":
                code.append("  " * indent + f"if ({stmt.condition}) {{")
                code.extend(unroll_block(stmt.true_branch, depth, indent + 1))
                code.append("  " * indent + "}")
                if stmt.false_branch:
                    code.append("  " * indent + "else {")
                    code.extend(unroll_block(stmt.false_branch, depth, indent + 1))
                    code.append("  " * indent + "}")
            elif stmt.type == "While" and depth > 0:
                for i in range(depth):
                    code.append("  " * indent + f"if ({stmt.condition}) {{")
                    code.extend(unroll_block(stmt.body, depth, indent + 1))
                    code.append("  " * indent + "}")
            elif stmt.type == "For" and depth > 0:
                init = stmt.init
                code.append("  " * indent + f"{init};")
                for i in range(depth):
                    code.append("  " * indent + f"if ({stmt.condition}) {{")
                    code.extend(unroll_block(stmt.body, depth, indent + 1))
                    code.append("  " * indent + f"  {stmt.update};")
                    code.append("  " * indent + "}")
        return code

    unrolled = unroll_block(ast, unroll_depth)
    return "\n".join(unrolled)

@app.route('/', methods=['GET', 'POST'])
def index():
    result = {"parsed": "", "ssa": "", "smt_result": "", "counterexamples": [], "error": "", "dot_file": "", "status": "", "unrolled": ""}
    code1 = ""
    code2 = ""
    depth = 3
    mode = "verify"

    if request.method == 'POST':
        code1 = request.form['code1'].strip()
        code2 = request.form.get('code2', '').strip()
        try:
            depth = int(request.form['depth'])
            if depth < 1:
                raise ValueError("Unroll depth must be at least 1")
        except ValueError as e:
            result["error"] = f"Invalid unroll depth: {str(e)}"
            return render_template('index.html', result=result, code1=code1, code2=code2, depth=depth, mode=mode)

        mode = request.form['mode']
        parser = Parser()

        try:
            if not code1:
                raise ValueError("Program 1 is required")
            if mode == "equivalence" and not code2:
                raise ValueError("Second program required for equivalence mode")

            logging.debug(f"Processing input: mode={mode}, depth={depth}")
            logging.debug(f"Code1:\n{code1}")
            if code2:
                logging.debug(f"Code2:\n{code2}")

            parse_result1 = parser.parse_program(code1)
            if isinstance(parse_result1, str):
                raise ValueError(parse_result1)
            ast1_dict, dot_file1, ast1_node = parse_result1
            result["parsed"] = json.dumps(ast1_dict, indent=2)
            result["dot_file"] = dot_file1

            # Generate unrolled code for Program 1
            result["unrolled"] = generate_unrolled_code(ast1_node, depth)

            ssa_converter = SSAConverter()
            ssa_instructions1 = ssa_converter.convert(ast1_node, unroll_depth=depth)
            result["ssa"] = "\n".join(str(instr) for instr in ssa_instructions1)

            smt_generator = SMTGenerator()
            smt_output = None
            z3_result = None

            # Process Program 2 for equivalence mode
            if mode == "equivalence":
                parser2 = Parser()
                parse_result2 = parser2.parse_program(code2)
                if isinstance(parse_result2, str):
                    raise ValueError(parse_result2)
                ast2_dict, dot_file2, ast2_node = parse_result2
                result["parsed"] += "\n\n=== Program 2 AST ===\n" + json.dumps(ast2_dict, indent=2)
                result["dot_file"] = dot_file1

                # Generate unrolled code for Program 2
                result["unrolled"] += "\n\n=== Program 2 Unrolled ===\n" + generate_unrolled_code(ast2_node, depth)

                ssa_converter2 = SSAConverter()
                ssa_instructions2 = ssa_converter2.convert(ast2_node, unroll_depth=depth)
                result["ssa"] += "\n\n=== Program 2 SSA ===\n" + "\n".join(str(instr) for instr in ssa_instructions2)

                smt_output = smt_generator.generate_smt(ssa_instructions1, mode="comparison", ssa_instructions2=ssa_instructions2)
            else:
                smt_output = smt_generator.generate_smt(ssa_instructions1, mode="verification")

            logging.debug(f"Raw SMT Output:\n{smt_output}")
            result["smt_result"] = smt_output

            z3_status, z3_model = run_z3(smt_output)
            result["counterexamples"] = z3_model
            result["status"] = z3_status

        except Exception as e:
            logging.error(f"Error in processing: {str(e)}")
            result["error"] = f"Error: {str(e)}"

    return render_template('index.html', result=result, code1=code1, code2=code2, depth=depth, mode=mode)

if __name__ == '__main__':
    app.run(debug=True)