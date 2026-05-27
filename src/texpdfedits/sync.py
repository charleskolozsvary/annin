"""Sync PDF coordinates with positions in the LaTeX file"""
from pathlib import Path
import subprocess
import re

def _run_synctex(
        pageno: int,
        x: int,
        y: int,
        output: Path,
        cwd: Path = Path('.'),
) -> str:
    """
    Args:
        pageno: one-indexed page number of annotated PDF
        x:      x position of annotation (in big points or modern pt)
        y:      y position of annotation (also in big points)
        output: path to file outputted by compilation of source with
                -synctex=1
    Returns:
        stdout of synctex as str provided it succeeded
    """
    command = (
        'synctex',
        'edit',
        '-o',
        f'{pageno}:{x}:{y}:{str(output)}',
    )
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"SyncTeX command not found: {command}") from e

    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"SyncTeX timed out") from e

    if result.returncode != 0:
        raise RuntimeError(f"SyncTeX returned nonzero: {result.stderr}")
        
    return result.stdout

def _parse_synctex_stdout(
        synctex_out: str,
        input_file: Path,        
        output_file: Path,
) -> int:
    """
    Args:
        synctex_out: stdout of synctex as str
        input_file:       path to source LaTeX file    
        output_file:      path to file outputted by compilation of souce
    
    Returns:
        LaTeX source line number outputted by synctex

    SyncTeX output looks like
    
    This is SyncTeX command line utility, version 1.5
    SyncTeX result begin
    Output:morelines_source.pdf
    Input:/Users/kolozsvary/github/corrinline/tests/regression/real_world/arxiv00/./morelines_source.tex
    Line:752
    Column:-1
    Offset:0
    Context:
    SyncTeX result end

    The column number is always -1 in my testing    
    """
    result_regex = r"SyncTeX result begin(.*?)SyncTeX result end"
    result_match = re.search(result_regex, synctex_out, flags = re.DOTALL)
    if result_match is None:
        raise ValueError(f"SyncTeX result is not of expected format: {synctex_out}")

    synctex_result = result_match.group(1)
    
    fields = ("Line", "Output", "Input")
    matches = {
        field: re.search(f"{field}:(.+)", synctex_result)
        for field in fields
    }
        
    for field, result_match in matches.items():
        if not result_match:
            raise ValueError(f"SyncTeX result did not contain {field}: {synctex_result}")

    line_match = matches["Line"].group(1).strip()
    try:
        line_no = int(line_match)
    except Exception as e:
        raise ValueError(f"SyncTeX line invalid: {line_match}") from e

    output_file_sync = Path(matches["Output"].group(1).strip())
    input_file_sync  = Path(matches["Input"].group(1).strip())

    if not output_file_sync.exists():
        raise FileNotFoundError(f"SyncTeX Output {output_file_sync} does not exist")
    
    if not input_file_sync.exists():
        raise FileNotFoundError(f"SyncTeX Input {input_file_sync} does not exist")

    if output_file_sync.name != output_file.name:
        raise ValueError(
            f"SyncTeX Output file {output_file_sync} does not "
            f"match expected output file {output_file.name}"
        )

    if input_file_sync.name != input_file.name:
        raise ValueError(
            f"SyncTeX Input file {input_file_sync} does not "
            f"match expected input file {input_file.name}"
        )

    return line_no

def build_line_map(path: Path) -> dict[int, tuple[int, int]]:
    """
    Return a dictionary with zero indexed line numbers as keys
    and zero indexed source positions as values

    res[0] = 0
    res[1] = position of first character on the second line of
             the file
    etc
    """
    if not path.exists():
        raise FileNotFoundError(f"Input file '{path}' does not exist")

    with open(path, 'r') as f:
        lines = f.readlines()        
    result = {}
    offset = 0    
    for line_no, line in enumerate(lines, start=1):
        result[line_no] = offset
        offset += len(line)
    return result

def rectangle_to_latex(
        pageno: int,
        in_rectangle: pymupdf.Rect,
        line2pos: dict[int, int],
        tex_str: str,
        input_file: Path,
        output_file: Path,
) -> tuple[str, tuple[int, int]]:
    """
    Args:
        pageno: zero indexed page from pymupdf
        in_rectangle: rectangle on the page 
        line2pos: maps 1 indexed line number character
                  index of start of line in LaTeX
        tex_str: original LaTeX source
        input_file: Path to LaTeX source file
        output_file: Path to output of LaTeX source 
    
    Returns:
        The original source latex with position ranges
        (str, (int, int))
    """
    pageno += 1 # make one indexed
    x, y = round(in_rectangle.x0), round(in_rectangle.y0)
    synctex_out = _run_synctex(pageno, x, y, output_file)
        
    line_no = _parse_synctex_stdout(synctex_out, input_file, output_file)
    
    if line_no not in line2pos:
        raise ValueError(f"Line number {line_no} out of range for {input_file}")
    
    # TODO enhance line finding with some heuristics informed by
    # parsing the LaTeX with pylatexenc.

    if line_no + 1 not in line2pos:
        line_no -= 1
        
    snippet_start = line2pos[line_no]
    snippet_end   = line2pos[line_no+1]
    latex_snippet = tex_str[snippet_start:snippet_end]
    
    return latex_snippet, (snippet_start, snippet_end), line_no

def improve_synctex_line(
        line_no: int,
        line2pos: dict[int, int],
        tex_str: str,
) -> int:
    r"""
    Use some simple heuristics to improve the line
    number given from SyncTeX. Primarily for
    \bibitem, \bib, \footnote, and \caption
    adjacent text. See notes/module_musings.md for more
    Args:
        line number from SyncTeX
        map from lines to start source positions in tex_str
        entire LaTeX source file as string
    Returns:
        (potentially) new line number
    """
    raise NotImplementedError()

