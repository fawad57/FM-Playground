# Formal Methods Playground

The Formal Methods Playground is a web-based tool designed to assist users in exploring formal verification and program equivalence checking. Built using Python, Flask, and the Z3 theorem prover, this project allows users to analyze programs by converting them into Static Single Assignment (SSA) form, generating SMT-LIB code, and using Z3 to verify properties or check equivalence between programs. The tool provides a user-friendly GUI with detailed outputs for ASTs, SSA, SMT, and counterexamples.

## Overview

- **Purpose**: To enable users to verify program assertions (Verification mode) or compare two programs for equivalence (Comparison mode).
- **Technologies**: Python, Flask, Z3, Graphviz.
- **Current Status**: Functional with support for loops, conditionals, assertions, and multiple variables.
- **Last Updated**: May 14, 2025.

## Features

- **Verification Mode**: Check if a program satisfies its assertions (e.g., `assert(x == 2)`).
- **Comparison Mode**: Determine if two programs produce the same final state.
- **AST Visualization**: View Abstract Syntax Trees (ASTs) as graphs using Graphviz.
- **SSA Conversion**: Converts programs into Static Single Assignment form for analysis.
- **SMT Generation**: Generates SMT-LIB code for the Z3 solver.
- **Counterexamples**: Displays counterexamples for failed assertions or equivalence results.
- **Customizable Unroll Depth**: Adjust loop unrolling for precise control over analysis.

## Prerequisites

Before running the project, ensure you have the following installed:

- **Python 3.7+**
- **Z3 Theorem Prover** (v4.15.0 or later, installed at `C:\\z3-4.15.0-x64-win\\bin\\z3.exe` for Windows)
- **Graphviz** (for AST visualization)
- **Python Packages**:
  - Flask
  - Graphviz

## Installation

Follow these steps to set up the project locally:

1. **Clone the Repository**:

   ```bash
   git clone https://github.com/fawad57/FM-Playground.git
   cd formal-methods-playground
   ```

2. **Install Python Dependencies**:

   ```bash
   pip install flask graphviz
   ```

3. **Install Z3**:

   - Download Z3 (v4.15.0) from [Z3 Releases](https://github.com/Z3Prover/z3/releases).
   - Extract it to `C:\z3-4.15.0-x64-win\` (or update the path in `app.py` if installed elsewhere).

4. **Install Graphviz**:
   - Download and install Graphviz from [Graphviz.org](https://graphviz.org/download/).
   - Add the Graphviz `bin` directory (e.g., `C:\Program Files\Graphviz\bin`) to your system PATH.

## Usage

1. **Run the Application**:

   ```bash
   python app.py
   ```

   - This will start a Flask server at `http://localhost:5000`.

2. **Access the GUI**:

   - Open your browser and go to `http://localhost:5000`.
   - **Input Program(s)**:
     - For **Verification Mode**, enter one program with an `assert` statement.
     - For **Comparison Mode**, enter two programs to compare.
   - **Select Mode**: Choose Verification or Comparison.
   - **Set Unroll Depth**: Specify the loop unrolling depth (e.g., 3).
   - **Submit**: Click "Analyze Program(s)" to view results.

3. **Output Tabs**:
   - **Parse**: Displays the AST(s) in JSON format and as a graph (if Graphviz is installed).
   - **SSA**: Shows the Static Single Assignment form of the program(s).
   - **SMT**: Displays the generated SMT-LIB code.
   - **Counterexamples**: Shows verification results (e.g., `sat`/`unsat`) and counterexamples or equivalence messages.

## Example Programs

### Verification Mode Examples

1. **Simple Loop with Correct Assertion**:

   ```plaintext
   x:=0;
   while(x < 2) {
       x:=x+1;
   }
   assert(x == 2)
   ```

   - **Expected Result**: `unsat` (assertion holds).

2. **Nested Loops with Multiple Variables**:

   ```plaintext
   x:=0;
   y:=0;
   while(x < 5) {
       x:=x+1;
       if (x < 3) {
           y:=y+2;
       } else {
           y:=y+1;
       }
   }
   assert(y == 8)
   ```

   - **Expected Result**: `unsat` (assertion holds).

3. **Complex Loop with Incorrect Assertion**:
   ```plaintext
   x:=0;
   y:=10;
   while(x < 4) {
       x:=x+1;
       if (x < 2) {
           y:=y-2;
       } else {
           if (x < 3) {
               y:=y-1;
           } else {
               y:=y+1;
           }
       }
   }
   assert(y == 5)
   ```
   - **Expected Result**: `sat` (assertion fails, `y = 9`).

### Comparison Mode Examples

1. **Equivalent Programs with Nested Loops**:

   - **Program 1**:
     ```plaintext
     x:=0;
     y:=0;
     while(x < 3) {
         x:=x+1;
         while(y < 2) {
             y:=y+1;
         }
     }
     ```
   - **Program 2**:
     ```plaintext
     x:=0;
     y:=0;
     while(x < 3) {
         x:=x+1;
     }
     while(y < 2) {
         y:=y+1;
     }
     ```
   - **Expected Result**: `sat` (programs are equivalent, both result in `x = 3`, `y = 2`).

2. **Non-Equivalent Programs with Complex Logic**:
   - **Program 1**:
     ```plaintext
     x:=0;
     y:=0;
     z:=0;
     while(x < 3) {
         x:=x+1;
         if (x < 2) {
             y:=y+2;
             z:=z+1;
         } else {
             y:=y+1;
             z:=z+2;
         }
     }
     ```
   - **Program 2**:
     ```plaintext
     x:=0;
     y:=0;
     z:=0;
     while(x < 3) {
         x:=x+1;
         if (x < 2) {
             y:=y+1;
             z:=z+2;
         } else {
             y:=y+2;
             z:=z+1;
         }
     }
     ```
   - **Expected Result**: `unsat` (programs are not equivalent, final states differ: `y = 4`, `z = 5` vs. `y = 5`, `z = 4`).

## Project Structure

- `app.py`: Main Flask application that handles the web server and core logic.
- `parser.py`: Parses input programs into Abstract Syntax Trees (ASTs).
- `ssa_converter.py`: Converts ASTs to Static Single Assignment (SSA) form.
- `smt_generator.py`: Generates SMT-LIB code for Z3.
- `index.html`: HTML template for the GUI.
- `static/style.css`: CSS file for styling the interface.
- `output.smt2`: Temporary file generated for Z3 input.
- `static/`: Directory for storing generated AST images.

## Testing

The project has been tested with various programs, including:

- Simple assignments and assertions.
- Loops with varying unroll depths.
- Nested conditionals and loops.
- Programs with multiple variables.

To test, run the example programs provided above and verify the outputs in the GUI tabs. If you encounter issues, check the terminal logs for debug information (e.g., `DEBUG: SSA for Program 1`, `DEBUG: SMT Output`).

## Troubleshooting

- **Z3 Not Found**: Ensure Z3 is installed at the specified path (`C:\\z3-4.15.0-x64-win\\bin\\z3.exe`). Update the path in `app.py` if necessary.
- **Graphviz Errors**: Verify that Graphviz is installed and added to your system PATH.
- **Timeout Issues**: Large programs may cause Z3 to timeout. Increase the timeout value in `app.py` (default is 60 seconds).
- **Parsing Errors**: Ensure your program syntax is correct (e.g., proper semicolons, balanced braces).

## Contributing

Contributions are welcome! To contribute:

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/your-feature`).
3. Commit your changes (`git commit -m "Add your feature"`).
4. Push to your branch (`git push origin feature/your-feature`).
5. Open a pull request on GitHub.

Please ensure your code follows the project’s coding style and includes appropriate tests.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contact

For questions or support, please open an issue on the GitHub repository or contact [fawadhumayun96@gmail.com].

## Acknowledgments

- **Z3 Theorem Prover**: For enabling formal verification.
- **Flask**: For providing a lightweight web framework.
- **Graphviz**: For AST visualization.
- Developed as part of a formal methods learning project.
