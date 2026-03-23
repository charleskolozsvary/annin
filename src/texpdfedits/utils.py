import logging
logger = logging.getLogger(__name__)

from pathlib import Path
import subprocess
import sys
import re

DEFAULT_LATEX_COMPILER = 'pdflatex'

DIFF_PDF_DPI = 175

COMPILER_INFO = {
    'pdflatex': (2, 'latin-1', ['--interaction=nonstopmode']),
    'prdlatex': (1, 'latin-1', ['-pdf', '-nonstopmode']),
    'xelatex': (2, 'utf-8', ['--interaction=nonstopmode'])
}

r"""
The tolerance of 50_000 pixels is a heuristic picked by trial and error.
Unfortunately, italic correction can still be inserted *before* a markbox, too, which will introduce some pixel differences.
Example: '(\emph{Boundary depletion})' (\markbox{}{\emph{Boundary depletion}}) will prevent space from being inserted after the
first open parenthesis if the entire string is in italic font.
"""
DIFFPDF_PER_PAGE_PIXEL_TOLERANCE = 50_000

INTERMEDIATE_EXTENSIONS_TO_DELETE = set(
    ".aux .out .log .toc .bbl .blg .thm "
    ".synctex.gz .synctex .brf .pdf"
    .split()
)

UTF2TEX = {
    '“': "``", #\u201C
    '”': "''", #\u201D
    '‘': "`", # \u2018
    '’': "'", # \u2019
    '§': r'\S ', # \u00A7
    '–': '--', # \u2013
    '—': '---', # \u2014
}

class TextProgressBar:
    def __init__(self, num_to_be_done):
        self.total = num_to_be_done
        self.bar_str = '|' + '-' * self.total + '|'
    def showSize(self):
        print(self.bar_str, end='\n ', flush=True)
    def addProgress(self):
        print('.', end='', flush=True)
    def end(self):
        print(flush=True)

def pdfFname(tex_fname: Path):
    return f"{tex_fname.stem}.pdf"        

def sourceAsString(filename: Path, **kwargs) -> str:
    enc = kwargs.get('encoding', 'utf-8')    
    with open(filename, 'r', encoding = enc) as f:
        tex_file_str = f.read()
    return tex_file_str

def writeStringToFile(string: str, filename: Path, **kwargs) -> int:
    enc = kwargs.get('encoding', 'utf-8')
    with open(filename, 'w', encoding = enc) as f:
        f.write(string)
    return 0        

def transferTeXFiles(
        tex_filename: Path,
        files_to: Path,
        move_or_copy: str
):
    logger.debug(
        f"the tex_filename is {tex_filename}\n"
        f"files_to is {files_to}"
    )
    if tex_filename.parent == files_to:
        logger.debug(
            "No need to transfer files; they are already in the cwd"
        )
        return
    
    tex_dot_star_files = [x for x in tex_filename.parent.glob(f'{tex_filename.stem}.*')]
    for x in tex_dot_star_files:
        match move_or_copy:
            case 'mv':
                x.move_into(files_to)
            case 'cp':
                x.copy_into(files_to)
            case _:
                logger.critical(
                    f"Could not transfer TeX files: "
                    f"unrecognized action '{move_or_copy}'; exiting"
                )
                sys.exit(1)

def removeDir(directory: Path):
    if not directory.exists():
        return
    files_in_dir = [f for f in directory.glob('**/*') if f.is_file()]
    if not files_in_dir:
        directory.rmdir()
        return
    for f in files_in_dir:
        f.unlink()
    directory.rmdir()

def compileLatex(
        tex_filename: Path,
        compiler: str = DEFAULT_LATEX_COMPILER
) -> subprocess.CompletedProcess:
    """Compile .tex file with provided compiler"""
    
    result = None
    tex_filename_dir = tex_filename.parent
    
    (num_runs, encoding, compile_options) = COMPILER_INFO.get(
        compiler,
        (2, 'latin-1', ['--interaction=nonstopmode'])
    )
    command = [compiler, *compile_options, tex_filename.name]    
    for i in range(num_runs):
        logger.info(
            f"Running {compiler} on {tex_filename} "
            f"(pass {i+1}/{num_runs})..."
        )
        logger.debug(f"I.e., {' '.join(command)}")        
        result = subprocess.run(
            command,
            cwd=tex_filename_dir,
            capture_output=True, # see result.stdout, result.stderr
            text=True,
            encoding=encoding
        )
        
        if result.returncode != 0:
            logger.error(
                f"{compiler} failed on pass {i+1} of "
                f"{tex_filename.name}: {result.stderr}."
                f"Output: {result.stdout}"
            )
            sys.exit(1)
        
    return result

def runDiffpdf(
        first_fname: str,
        second_fname: str,
        output_dir: Path,
        per_page_tol: int = DIFFPDF_PER_PAGE_PIXEL_TOLERANCE
) -> subprocess.CompletedProcess:
    
    first_stem = Path(first_fname).stem
    second_stem = Path(second_fname).stem
    diff_fname = f'diff_{first_stem}_{second_stem}.pdf'

    subprocess_command = [
        'diff-pdf',
        f'--per-page-pixel-tolerance={per_page_tol}',
        f'--dpi={DIFF_PDF_DPI}',
        '--skip-identical',
        '--grayscale',
        '--mark-differences',
        '--verbose',
        f'--output-diff={diff_fname}',
        first_fname,
        second_fname
    ]
    
    logger.info(f"Running `{' '.join(subprocess_command)}`...")
    
    result = subprocess.run(
        subprocess_command,
        cwd=output_dir
    )
    
    if result.returncode != 0:
        logger.error(
            f"{first_fname} and {second_fname} are not identical. "
            f"See {Path(output_dir) / diff_fname}"
        )
        sys.exit(1)
        
    return (result, Path(diff_fname))
    
def deleteIntermediateLaTeX(tex_filename: Path):
    body = tex_filename.stem
    for extension in INTERMEDIATE_EXTENSIONS_TO_DELETE:
        to_delete = Path(body + extension)
        if to_delete.exists():
            logger.debug(f"Deleted {to_delete}")
            to_delete.unlink()
            
def replaceNewlines(s: str) -> str:
    return re.sub(r'[\n\r]', r' ', s)

def backslashEscape(s: str) -> str:
    return s.replace('\\', r'\\')

def UTFtoTeX(s: str) -> str:
    return ''.join(
        UTF2TEX.get(char, char)
        for char in s
    )
