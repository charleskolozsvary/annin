"""Sync PDF coordinates with positions in the LaTeX file"""
from pathlib import Path
import subprocess
import re

MACROS_IMPROVE_START = {
    'caption' : '[{',
    'bibitem' : '[{',
    'bib'     : '{{{',
    'footnote': '[{',
}

ENVS_IMPROVE_START = (
    'equation',
    'align',
    'multline',
)

OTHER_IMPROVE_START = {
    r'\\\[': r'\\\]',
    r'\$\$': r'\$\$',
}

NUM_LINES_LOOK_BEHIND = 20
NUM_LINES_LOOK_AHEAD = 30

def _read_balanced(string: str, delimiters: tuple[str, str]) -> tuple[int, int] | None:
    start_delim, end_delim = delimiters
    encountered_open = False
    idx, stack, start_balanced = 0, 0, 0
    while idx < len(string):
        char = string[idx]
        substr = char
        while start_delim.startswith(substr) and idx < len(string):
            if substr == start_delim:
                if not encountered_open:
                    start_balanced = idx - len(substr) + 1
                    encountered_open = True
                stack += 1
                break
            idx += 1
            char = string[idx]
            substr += char
        while end_delim.startswith(substr) and idx < len(string):
            if substr == end_delim:
                stack -= 1
                break
            idx += 1
            char = string[idx]
            substr += char
        idx += 1
        if not stack and encountered_open:
            return (start_balanced, idx)
    return None

def _macro_end_sync(
        ahead_str: str,
        tex_read_start: int,
        synctex_line_start: int,
        macro_name: str,
) -> int:
    raise NotImplementedError()

def _env_end_sync(
        ahead_str: str,
        tex_read_start: int,
        synctex_line_start: int,
        env_name: str,
) -> int:
    raise NotImplementedError()

def _other_end_sync(
        ahead_str: str,
        tex_read_start: int,
        synctex_line_start: int,
        other_name: str,
) -> int:
    raise NotImplementedError()

def _end_synctex_span(
        tex_str: str,
        last_match: re.Match,
        match_snippet_start: int,
        line: int,
        line2pos: dict[int, int],
) -> int:
    try:
        match_type = ('macro', last_match.span('macro'))
    except IndexError as e:
        try: 
            match_type = ('env', last_match.span('env'))
        except IndexError as e:
            match_type = ('other', last_match.span('other'))
    group_id, group_span = match_type
    
    read_start = group_span[1] + match_snippet_start
    
    end_line = line + NUM_LINES_LOOK_AHEAD
    if end_line not in line2pos:
        end_line = max(line2pos)
        
    ahead_str = tex_str[read_start:line2pos[end_line]]
    args = ahead_str, read_start, line2pos[line], last_match.group(group_id)
    if group_id == 'macro':
        return _macro_end_sync(*args)
    elif group_id == 'env':
        return _env_end_sync(*args)
    else:
        return _other_end_sync(*args)
    

def _improve_synctex_span(
        tex_str: str,
        line: int,
        line2pos: dict[int, int]
) -> tuple[int, int]:
    if line + 2 not in line2pos:
        line -= 2        
    start, end = line2pos[line - NUM_LINES_LOOK_BEHIND], line2pos[line + 1]
    behind_str = tex_str[start:end]
    envs = [
        rf'\\begin\s*{{(?P<env>{env}\*?)}}'
        for env in ENVS_IMPROVE_START
    ]
    macros = [
        rf'\\(?P<macro>{macro})\b'
        for macro in MACROS_IMPROVE_START
    ]
    other = [
        rf'(?P<other>{other})'
        for other in OTHER_IMPROVE_START
    ]
    regex = '|'.join(envs + macros + other)
    
    matches = list(re.finditer(regex, behind_str))
    if not matches:
        return line2pos[line - 1], line2pos[line + 2]
    last_match = matches[-1]
    synctex_span = (
        start + last_match.span()[0],
        _end_synctex_span(tex_str, last_match, start)
    )
    return synctex_span

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

    snippet_start, snippet_end = _improve_synctex_span(line_no, line2pos, tex_str)
    
    latex_snippet = tex_str[snippet_start:snippet_end]
    
    return latex_snippet, (snippet_start, snippet_end), line_no

