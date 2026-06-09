"""Sync PDF coordinates with positions in the LaTeX file"""
from pathlib import Path
import subprocess
import re
from icecream import ic

OPT = ('[', ']')
REQ = ('{', '}')

MACROS_IMPROVE_START = {
    'chapter'        : (OPT, REQ),    
    'section'        : (OPT, REQ),
    'subsection'     : (OPT, REQ),
    'subsubsection'  : (OPT, REQ),
    'chapter*'       : (OPT, REQ),        
    'section*'       : (OPT, REQ),
    'subsection*'    : (OPT, REQ),
    'subsubsection*' : (OPT, REQ),
    'caption'        : (OPT, REQ),
    'bib'            : (REQ, REQ, REQ),
    'footnote'       : (OPT, REQ),
    'caption*'       : (OPT, REQ),    
}

ENVS_IMPROVE_START = (
    'equation',
    'align',
    'multline',
    'gather',
)

OTHER_IMPROVE_START = {
    r'\[': r'\]',
    r'\bibitem': '\n\n', # I want the entire bibitem until blank line
}

NUM_LINES_LOOK_BEHIND = 20
NUM_LINES_LOOK_AHEAD = 30

def _read_balanced(string: str, delimiters: tuple[str, str]) -> tuple[int, int] | None:
    start_delim, end_delim = delimiters
    if start_delim == end_delim or start_delim.startswith(end_delim):
        raise ValueError(
            f"either '{start_delim}' == {end_delim} "
            f"or '{start_delim}'.startswith('{end_delim}')"
        )
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
            if idx >= len(string):
                ic(f'string ended while searching for {start_delim}')
                return None
            char = string[idx]
            substr += char
        while end_delim.startswith(substr) and idx < len(string):
            if substr == end_delim:
                stack -= 1
                break
            idx += 1
            if idx >= len(string):
                ic(f'string ended while searching for {end_delim}')
                return None            
            char = string[idx]
            substr += char
        idx += 1
        if not stack and encountered_open:
            return (start_balanced, idx)
    return None

def _first_line_after_char(char_idx: int | None, line2pos: dict[int, int]) -> int | None:
    if char_idx is None:
        return None
    lines_after_char = sorted(
        line for line, line_start in line2pos.items()
        if line_start >= char_idx
    )
    if not lines_after_char:
        return None
    return lines_after_char[0]

def _first_line_before_char(char_idx: int | None, line2pos: dict[int, int]) -> int | None:
    if char_idx is None:
        return None
    lines_before_char = sorted(
        line for line, line_start in line2pos.items()
        if line_start <= char_idx
    )
    if not lines_before_char:
        return None
    return lines_before_char[-1]

def _macro_end_sync(
        ahead_str: str,
        tex_read_start: int,
        synctex_line_start: int,
        macro_name: str,
) -> int:
    arg_signature = MACROS_IMPROVE_START[macro_name]
    read_str = ahead_str
    macro_arg_read_end = tex_read_start # point read up to by macro args
    for arg in arg_signature:
        # ic(macro_arg_read_end)
        arg_span = _read_balanced(read_str, arg)
        if arg_span is None and arg == REQ:
            return None
        if arg_span is None and arg == OPT:
            continue
        
        to_arg_start = read_str[:arg_span[0]]
        if re.match(r'^[ \t\r]*$', to_arg_start) is None:
            # expect argument like \caption<single line whitespace><arg>
            if arg == REQ:
                # ic(to_arg_start, arg)
                return None
            if arg == OPT:
                # ic(to_arg_start, arg)                
                continue

        start, end = arg_span
        macro_arg_read_end += end
        read_str = read_str[end:]
    if macro_arg_read_end >= synctex_line_start:
        return macro_arg_read_end
    else:
        # ic(macro_arg_read_end >= synctex_line_start)
        # if the macro args don't actually contain
        # (read up to) the original synctex line
        return None

def _env_end_sync(
        ahead_str: str,
        tex_read_start: int,
        synctex_line_start: int,
        env_name: str,
        delimiters: tuple[str, str],
) -> int:
    env_span = _read_balanced(ahead_str, delimiters)
    if env_span is None:
        ic('_read_balanced returned None')
        return None
    _, env_read_end = env_span
    tex_read_end = tex_read_start + env_read_end # point read up to by environment 
    if tex_read_end >= synctex_line_start:
        return tex_read_end
    else:
        ic(tex_read_end >= synctex_line_start)
        return None

def _end_synctex_line(
        tex_str: str,
        last_match: re.Match,
        match_snippet_start: int,
        line: int,
        line2pos: dict[int, int],
        improved_start_line: int,
) -> int:
    ids = ['macro', 'env', 'other']
    for gid in ids:
        if last_match.group(gid) is not None:
            group_id = gid
            break
    if group_id == 'macro':
        # read past \csname to read args
        tex_read_start = match_snippet_start + last_match.span()[1]
    else:
        tex_read_start = match_snippet_start + last_match.span()[0]
    
    end_line = line + NUM_LINES_LOOK_AHEAD
    if end_line not in line2pos:
        end_line = max(line2pos)
        
    ahead_str = tex_str[tex_read_start:line2pos[end_line]]
    # ic(ahead_str)
    args = (
        ahead_str,
        tex_read_start,
        line2pos[line],
        last_match.group(group_id)
    )
    if group_id == 'macro':
        improved_end = _macro_end_sync(*args)
    elif group_id == 'env':
        env_name = last_match.group(group_id)
        ic(env_name)
        delimiters = (rf'\begin{{{env_name}}}', rf'\end{{{env_name}}}')
        improved_end = _env_end_sync(*args, delimiters)
    elif group_id == 'other': # other env, really
        s_delim = last_match.group(group_id)
        delimiters = (s_delim, OTHER_IMPROVE_START[s_delim])
        # ic(delimiters)
        improved_end = _env_end_sync(*args, delimiters)
        
    if improved_end is None:
        ic('improved_end is None')
        return None

    improved_end_line = _first_line_after_char(improved_end, line2pos)
    # ic(improved_end)
    if group_id == 'other' and s_delim == r'\bibitem':
        better_end_lines = [
            line for line in [improved_end_line, improved_end_line - 1]
            if line > improved_start_line            
        ]
        if better_end_lines:
            improved_end_line = min(better_end_lines)
            
    return improved_end_line
        
def _improve_synctex_line(
        tex_str: str,
        line: int,
        line2pos: dict[int, int]
) -> tuple[int, int]:
    if line + 2 not in line2pos:
        line -= 2        
    line_start, line_end = line2pos[line - NUM_LINES_LOOK_BEHIND], line2pos[line + 1]
    behind_str = tex_str[line_start:line_end]
    
    envs = '|'.join(
        rf'{env}\*?'
        for env in ENVS_IMPROVE_START
    )
    envs = rf'\\begin\s*{{(?P<env>{envs})}}'
    
    macros = '|'.join(
        csname for csname in MACROS_IMPROVE_START
    )
    macros = rf'\\(?P<macro>{macros})\b'

    others = '|'.join(
        # don't want to match \\[3em] in display math        
        r'(?<!\\)\\\[' if other == r'\[' else re.escape(other)   
        for other in OTHER_IMPROVE_START
    )
    others = rf'(?P<other>{others})'
    
    regex = '|'.join([envs, macros, others])    
    matches = list(re.finditer(regex, behind_str))

    # synctex is almost always correct when it is just tracing to
    # a simple word in the body of the document. It's not
    # worth extending the lines all the time because then more snippets
    # will merge than necessary. The whole point of _improve_synctex_line
    # is to extend the lines when it is appropriate
    default_start_line = line # line before line - 1
    default_end_line   = line + 1 # line after line + 2

    default_start_char = line2pos[default_start_line]
    default_end_char   = line2pos[default_end_line]    

    print('----------------------------------\n\n')
    ic(line, line2pos[line])
    # ic(tex_str[default_start_char:default_end_char])
    # ic(matches)
    
    if not matches:
        return default_start_line, default_end_line

    last_match = matches[-1]

    ic(last_match)
    improved_start = line_start + last_match.span()[0]
    improved_start_line = _first_line_before_char(improved_start, line2pos)    
    improved_end_line = _end_synctex_line(
        tex_str,
        last_match,
        line_start,
        line,
        line2pos,
        improved_start_line,
    )

    # ic(improved_end_line)
    
    if improved_end_line is None:
        return default_start_line, default_end_line

    # improved_end = line2pos[improved_line_end]
    # improved_start = line_start + last_match.span()[0]
    # improved_start_line = _first_line_before_char(improved_start, line2pos)
    # ic(improved_start_line)
    
    if improved_start_line >= improved_end_line:
        raise RuntimeError(f"'improved' start and ends invalid: {improved_start_line} > {improved_end_line}")

    ic(tex_str[line2pos[improved_start_line]:line2pos[improved_end_line]])
    
    return improved_start_line, improved_end_line

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

    line_start, line_end = _improve_synctex_line(tex_str, line_no, line2pos)

    snippet_start, snippet_end = line2pos[line_start], line2pos[line_end]
    
    latex_snippet = tex_str[snippet_start:snippet_end]
    
    return latex_snippet, (snippet_start, snippet_end), line_no

