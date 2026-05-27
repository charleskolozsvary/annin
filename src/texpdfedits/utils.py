import logging
logger = logging.getLogger(__name__)

from pathlib import Path
import subprocess
import sys
import re

DEFAULT_LATEX_COMPILER = 'pdflatex'

DIFF_PDF_DPI = 175

COMPILER_INFO = {
    'pdflatex': (2, 'latin-1', ['--interaction=nonstopmode', '-synctex=1'], 'pdf'),
    'prdlatex': (1, 'latin-1', ['-nonstopmode', '-synctex'], 'dvi'),
    'xelatex': (2, 'utf-8', ['--interaction=nonstopmode', '-synctex=1'], 'pdf')
}

INTERMEDIATE_EXTENSIONS_TO_DELETE = set(
    ".aux .out .log .toc .bbl .blg .thm "
    ".synctex.gz .synctex .brf .pdf"
    .split()
)

PDF_WORKFLOW = [
    'cams',
    'gsm',
    'stml',
    'amstext',
]

class PDFDiff(RuntimeError):
    pass

UNICODE2TEX = {
    # COMMON PUNCTUATION
    '\u201c': r"``",      # “ 
    '\u201d': r"''",      # ” 
    '\u2018': r"`",       # ‘ 
    '\u2019': r"'",       # ’ 
    '\u00a7': r'\S ',    # § 
    '\u2013': r'--',      # – (EN-DASH)
    '\u2014': r'---',     # — (EM-DASH)
    # LIGATURES
    '\ufb00': r'ff',      # ﬀ 
    '\ufb01': r'fi',      # ﬁ 
    '\ufb02': r'fl',      # ﬂ 
    '\ufb03': r'ffi',     # ﬃ
    '\ufb04': r'ffl',     # ﬄ
    '\u0132': r'{\IJ }',  # Ĳ
    '\u0133': r'{\ij }',  # ĳ    
    # MATH 
    '\u2206': r'\Delta',  # ∆
    '\u03a9': r'\Omega',  # Ω
    '\u03c9': r'\omega',  # ω
    # ACCENTED/SPECIAL LETTERS
    '\u00e0': r'{\` a}',  # à
    '\u00e1': r"{\' a}",  # á
    '\u00e2': r'{\^ a}',  # â
    '\u00e3': r'{\~ a}',  # ã
    '\u00e4': r'{\" a}',  # ä
    '\u00e5': r'{\r a}',  # å
    '\u00e6': r'{\ae }',  # æ
    '\u00e7': r'{\c c}',  # ç
    '\u00e8': r'{\` e}',  # è
    '\u00e9': r"{\' e}",  # é
    '\u00ea': r'{\^ e}',  # ê
    '\u00eb': r'{\" e}',  # ë
    '\u00ec': r'{\` i}',  # ì
    '\u00ed': r"{\' i}",  # í
    '\u00ee': r'{\^ i}',  # î
    '\u00ef': r'{\" i}',  # ï
    '\u00f0': r'{\dh }',  # ð
    '\u00f1': r'{\~ n}',  # ñ
    '\u00f2': r'{\` o}',  # ò
    '\u00f3': r"{\' o}",  # ó
    '\u00f4': r'{\^ o}',  # ô
    '\u00f5': r'{\~ o}',  # õ
    '\u00f6': r'{\" o}',  # ö
    '\u00f8': r'{\o  }',  # ø
    '\u00f9': r'{\` u}',  # ù
    '\u00fa': r"{\' u}",  # ú
    '\u00fb': r'{\^ u}',  # û
    '\u00fc': r'{\" u}',  # ü
    '\u00fd': r"{\' y}",  # ý
    '\u00fe': r'{\th }',  # þ
    '\u00ff': r'{\" y}',  # ÿ
    '\u0100': r'{\= A}',  # Ā
    '\u0101': r'{\= a}',  # ā
    '\u0102': r'{\u A}',  # Ă
    '\u0103': r'{\u a}',  # ă
    '\u0104': r'{\k A}',  # Ą
    '\u0105': r'{\k a}',  # ą
    '\u0106': r"{\' C}",  # Ć
    '\u0107': r"{\' c}",  # ć
    '\u0108': r'{\^ C}',  # Ĉ
    '\u0109': r'{\^ c}',  # ĉ
    '\u010a': r'{\. C}',  # Ċ
    '\u010b': r'{\. c}',  # ċ
    '\u010c': r'{\v C}',  # Č
    '\u010d': r'{\v c}',  # č
    '\u010e': r'{\v D}',  # Ď
    '\u010f': r"{d'}",    # ď
    '\u0110': r'{\DH }',  # Đ
    '\u0111': r'{\dj }',  # đ
    '\u0112': r'{\= E}',  # Ē
    '\u0113': r'{\= e}',  # ē
    '\u0114': r'{\u E}',  # Ĕ
    '\u0115': r'{\u e}',  # ĕ
    '\u0116': r'{\. E}',  # Ė
    '\u0117': r'{\. e}',  # ė
    '\u0118': r'{\k E}',  # Ę
    '\u0119': r'{\k e}',  # ę
    '\u011a': r'{\v E}',  # Ě
    '\u011b': r'{\v e}',  # ě
    '\u011c': r'{\^ G}',  # Ĝ
    '\u011d': r'{\^ g}',  # ĝ
    '\u011e': r'{\u G}',  # Ğ
    '\u011f': r'{\u g}',  # ğ
    '\u0120': r'{\. G}',  # Ġ
    '\u0121': r'{\. g}',  # ġ
    '\u0122': r'{\c G}',  # Ģ
    '\u0123': r'{\c g}',  # ģ
    '\u0124': r'{\^ H}',  # Ĥ
    '\u0125': r'{\^ h}',  # ĥ
    '\u0128': r'{\~ I}',  # Ĩ
    '\u0129': r'{\~ \i}', # ĩ
    '\u012a': r'{\= I}',  # Ī
    '\u012b': r'{\= \i}', # ī
    '\u012c': r'{\u I}',  # Ĭ
    '\u012d': r'{\u \i}', # ĭ
    '\u012e': r'{\k I}',  # Į
    '\u012f': r'{\k i}',  # į
    '\u0130': r'{\. I}',  # İ
    '\u0131': r'{\i  }',  # ı
    '\u0134': r'{\^J }',  # Ĵ
    '\u0135': r'{\^\j}',  # ĵ
    '\u0136': r'{\c K}',  # Ķ
    '\u0137': r'{\c k}',  # ķ
    '\u0139': r"{\' L}",  # Ĺ
    '\u013a': r"{\' l}",  # ĺ
    '\u013b': r'{\c L}',  # Ļ
    '\u013c': r"{\c l}",  # ļ
    '\u013d': r"{L'}",    # Ľ
    '\u013e': r"{l'}",    # ľ
    '\u0141': r'{\L}',    # Ł
    '\u0142': r'{\l}',    # ł
    '\u0143': r"{\' N}",  # Ń
    '\u0144': r"{\' n}",  # ń
    '\u0145': r'{\c N}',  # Ņ
    '\u0146': r'{\c n}',  # ņ
    '\u0147': r'{\v N}',  # Ň
    '\u0148': r'{\v n}',  # ň
    '\u014a': r'{\NG }',  # Ŋ
    '\u014b': r'{\ng }',  # ŋ
    '\u014c': r'{\= O}',  # Ō
    '\u014d': r'{\= o}',  # ō
    '\u014e': r'{\u O}',  # Ŏ
    '\u014f': r'{\u o}',  # ŏ
    '\u0150': r'{\H O}',  # Ő
    '\u0151': r'{\H o}',  # ő
    '\u0152': r'{\OE }',  # Œ
    '\u0153': r'{\oe }',  # œ
    '\u0154': r"{\' R}",  # Ŕ
    '\u0155': r"{\' r}",  # ŕ
    '\u0156': r'{\c R}',  # Ŗ
    '\u0157': r'{\c r}',  # ŗ
    '\u0158': r'{\v R}',  # Ř
    '\u0159': r'{\v r}',  # ř
    '\u015a': r"{\' S}",  # Ś
    '\u015b': r"{\' s}",  # ś
    '\u015c': r'{\^ S}',  # Ŝ
    '\u015d': r'{\^ s}',  # ŝ
    '\u015e': r'{\c S}',  # Ş
    '\u015f': r'{\c s}',  # ş
    '\u0160': r'{\v S}',  # Š
    '\u0161': r'{\v s}',  # š
    '\u0162': r'{\c T}',  # Ţ
    '\u0163': r'{\c t}',  # ţ
    '\u0164': r'{\v T}',  # Ť
    '\u0168': r'{\~ U}',  # Ũ
    '\u0169': r'{\~ u}',  # ũ
    '\u016a': r'{\= U}',  # Ū
    '\u016b': r'{\= u}',  # ū
    '\u016c': r'{\u U}',  # Ŭ
    '\u016d': r'{\u u}',  # ŭ
    '\u016e': r'{\r U}',  # Ů
    '\u016f': r'{\r u}',  # ů
    '\u0170': r'{\H U}',  # Ű
    '\u0171': r'{\H u}',  # ű
    '\u0172': r'{\k U}',  # Ų
    '\u0173': r'{\k u}',  # ų
    '\u0174': r'{\^ W}',  # Ŵ
    '\u0175': r'{\^ w}',  # ŵ
    '\u0176': r'{\^ Y}',  # Ŷ
    '\u0177': r'{\^ y}',  # ŷ
    '\u0178': r'{\" Y}',  # Ÿ
    '\u0179': r"{\' Z}",  # Ź
    '\u017a': r"{\' z}",  # ź
    '\u017b': r'{\. Z}',  # Ż
    '\u017c': r'{\. z}',  # ż
    '\u017d': r'{\v Z}',  # Ž
    '\u017e': r'{\v z}',  # ž
    '\u01cd': r'{\v A}',  # Ǎ
    '\u01ce': r'{\v a}',  # ǎ
    '\u01cf': r'{\v I}',  # Ǐ
    '\u01d0': r'{\v\i}',  # ǐ
    '\u01d1': r'{\v O}',  # Ǒ
    '\u01d2': r'{\v o}',  # ǒ
    '\u01d3': r'{\v U}',  # Ǔ
    '\u01d4': r'{\v u}',  # ǔ
    '\u01e2': r'{\=\AE}', # Ǣ
    '\u01e3': r'{\=\ae}', # ǣ
    '\u01e6': r'{\v G}',  # Ǧ
    '\u01e7': r'{\v g}',  # ǧ         
    '\u01e8': r'{\v K}',  # Ǩ               
    '\u01e9': r'{\v k}',  # ǩ
    '\u01ea': r'{\k O}',  # Ǫ               
    '\u01eb': r'{\k o}',  # ǫ               
    '\u01f0': r'{\v J}',  # ǰ               
    '\u01f4': r'{\' G}',  # Ǵ               
    '\u01f5': r'{\' g}',  # ǵ
}

class TextProgressBar:
    def __init__(self, num_to_be_done):
        self.total = num_to_be_done
        self.bar_str = '|' + '-' * self.total + '|'
    def show_size(self):
        print(self.bar_str, end='\n ', flush=True)
    def add_progress(self):
        print('.', end='', flush=True)
    def end(self):
        print(flush=True)

def sanitize_pdf_text(text: str):
    return unicode_to_tex(replace_newlines(text))

def _pdf_fname(tex_fname: Path):
    return f"{tex_fname.stem}.pdf"        

def source_as_string(filename: Path, **kwargs) -> str:
    enc = kwargs.get('encoding', 'utf-8')    
    with open(filename, 'r', encoding = enc) as f:
        tex_file_str = f.read()
    return tex_file_str

def write_string_to_file(string: str, filename: Path, **kwargs) -> int:
    enc = kwargs.get('encoding', 'utf-8')
    with open(filename, 'w', encoding = enc) as f:
        f.write(string)
    return 0

def tag_file_stem(file: Path, tag: str) -> Path:
    return file.parent / f"{file.stem}_{tag}{file.suffix}"

def new_tagged_fname(
        file: Path,
        tag: str,
        new_suffix: str = '',
        put_front: bool = False,        
) -> Path:
    if put_front:
        return Path(f"{tag}_{file.stem}{new_suffix if new_suffix else file.suffix}")
    else:
        return Path(f"{file.stem}_{tag}{new_suffix if new_suffix else file.suffix}")

def _transfer_tex_files(
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

def remove_dir(directory: Path):
    if not directory.exists():
        return
    files_in_dir = [f for f in directory.glob('**/*') if f.is_file()]
    if not files_in_dir:
        directory.rmdir()
        return
    for f in files_in_dir:
        f.unlink()
    directory.rmdir()

def _exchange_suffix(file: Path, suffix_no_dot: str) -> Path:
    return Path(f"{file.parent / file.stem}.{suffix_no_dot}")

def compile_latex(
        tex_file: Path,
        compiler: str = DEFAULT_LATEX_COMPILER
) -> Path:
    """
    Compile .tex file with provided compiler
    Args:
        tex_file: latex file to compile
        compiler:     name of LaTeX compiler
    
    Returns:
        Path: pathlib Path object of outputted file from compilation
    """
    tex_file_dir = tex_file.parent
    
    (num_runs, encoding, compile_options, output_extension) = COMPILER_INFO.get(
        compiler,
        (
            2,
            'latin-1',
            ['--interaction=nonstopmode', '-synctex=1'],
            'pdf'
        )
    )
    command = [compiler, *compile_options, tex_file.name]
    for i in range(num_runs):
        logger.info(
            f"Running {compiler} on {tex_file} "
            f"(pass {i+1}/{num_runs})..."
        )
        logger.debug(f"I.e., {' '.join(command)}")

        try:
            result = subprocess.run(
                command,
                cwd=tex_file_dir,
                capture_output=True, # see result.stdout, result.stderr
                text=True,
                encoding=encoding
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"Unable to locate binary: {command[0]}") from e
        
        if result.returncode != 0:
            logger.critical(
                f"{compiler} failed on pass {i+1} of "
                f"{tex_file.name}: {result.stderr}."
                f"Output: {result.stdout}"
            )
            raise RuntimeError("Compilation failed: see log for details")

    output_file = _exchange_suffix(tex_file, output_extension)
    if not output_file.exists():
        logger.critical(f"Could not find output of LaTeX compilation '{output_file}'")
        raise RuntimeError("Expected LaTeX output does not exist")

    return output_file

def run_diff_pdf(
        first_fname: Path,
        second_fname: Path,
        output_dir: Path = Path('.'),
        per_page_tol: int = 0
) -> subprocess.CompletedProcess:
    
    first_stem = first_fname.stem
    second_stem = second_fname.stem
    diff_fname = f'diff_{first_stem}_{second_stem}.pdf'

    command = [
        'diff-pdf',
        f'--per-page-pixel-tolerance={per_page_tol}',
        f'--dpi={DIFF_PDF_DPI}',
        '--skip-identical',
        '--grayscale',
        '--mark-differences',
        '--verbose',
        f'--output-diff={diff_fname}',
        first_fname.name,
        second_fname.name
    ]
    
    logger.info(f"Running `{' '.join(command)}`...")

    try:
        result = subprocess.run(
            command,
            cwd=output_dir
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"Unable to locate binary: {command[0]}") from e
        
    if result.returncode != 0:
        logger.error(
            f"{first_fname} and {second_fname} are not identical. "
            f"See {Path(output_dir) / diff_fname}"
        )
        raise PDFDiff("Detected PDF differences")
        
    return Path(diff_fname)
    
def delete_intermediate_latex(tex_file: Path):
    body = tex_file.stem
    for extension in INTERMEDIATE_EXTENSIONS_TO_DELETE:
        to_delete = Path(body + extension)
        if to_delete.exists():
            logger.debug(f"Deleted {to_delete}")
            to_delete.unlink()
            
def replace_newlines(s: str) -> str:
    return re.sub(r'[\n\r]', r' ', s)

def backslash_escape(s: str) -> str:
    return s.replace('\\', r'\\')

def unicode_to_tex(s: str) -> str:
    return ''.join(
        UNICODE2TEX.get(char, char)
        for char in s
    )

def compile_validate_clean(tex_file1: Path, tex_file2: Path, cwd: Path, **kwargs):
    compiler = kwargs.get('compiler', DEFAULT_LATEX_COMPILER)
    validate = kwargs.get('validate', True)
    clean    = kwargs.get('clean', True)
    replace  = kwargs.get('replace', False)
    
    process1 = compile_latex(tex_file1, compiler=compiler)
    process2 = compile_latex(tex_file2, compiler=compiler)

    _transfer_tex_files(tex_file1, cwd, 'cp')
    _transfer_tex_files(tex_file2, cwd, 'mv')

    pdf_file1 = _pdf_fname(tex_file1)
    pdf_file2 = _pdf_fname(tex_file2)
    
    if validate:
        diff_fname = run_diff_pdf(
            pdf_file1,
            pdf_file2,
            cwd,
            per_page_tol=0
        )

    logger.info(f"{pdf_file1} and {pdf_file2} are identical")

    if clean:
        logger.info("Deleting intermediate files.")
        diff_fname.unlink()
        delete_intermediate_latex(tex_file1)
        delete_intermediate_latex(tex_file2)

    if replace:
        # overwrite first file with second 
        tex_file2.move(tex_file1)
        logger.info(f"Overwrote {tex_file1} with {tex_file2}")
        
def plural(num: int):
    return 's' if num > 1 else ''
