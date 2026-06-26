import logging
logger = logging.getLogger(__name__)

from pathlib import Path
from datetime import datetime
import subprocess
import re

DEFAULT_LATEX_COMPILER = 'pdflatex'

DIFF_PDF_DPI = 175

COMPILER_INFO = {
    'pdflatex': (2, 'latin-1', ['--interaction=nonstopmode']),
    'prdlatex': (1, 'latin-1', ['-nonstopmode']),
    'xelatex': (2, 'utf-8', ['--interaction=nonstopmode']),
    'luatex': (2, 'utf-8', ['--interaction=nonstopmode'])    
}

INLINED_TAG = 'inlined'
AUTO_TAG = 'autocorrected'

MAX_ROMAN = 2001

r"""
The tolerance of 50_000 pixels is a heuristic picked by trial and error.
Unfortunately, italic correction can still be inserted *before* a markbox, too, which will introduce some pixel differences.
Example: '(\emph{Boundary depletion})' (\markbox{}{\emph{Boundary depletion}}) will prevent space from being inserted after the
first open parenthesis if the entire string is in italic font.
"""
DIFFPDF_PER_PAGE_PIXEL_TOLERANCE = 50_000

INTERMEDIATE_EXTENSIONS_TO_DELETE = set(
    ".aux .out .log .toc .bbl .blg .thm "
    ".synctex.gz .synctex .brf .pdf .dvi"
    .split()
)

PDF_WORKFLOW = [
    'cams',
    'gsm',
    'stml',
    'amstext',
]

SELECTION_TAG = 'SEL'

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
    def showSize(self):
        print(self.bar_str, end='\n ', flush=True)
    def addProgress(self):
        print('.', end='', flush=True)
    def end(self):
        print(flush=True)

def sanitize_pdf_text(text: str):
    return UnicodeToTeX(replaceNewlines(text))

def pdf_name(tex_fname: Path) -> Path:
    return Path(f"{tex_fname.stem}.pdf")

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

def tagFileStem(file: Path, tag: str) -> Path:
    return file.parent / f"{file.stem}_{tag}{file.suffix}"

def newTaggedFname(
        file: Path,
        tag: str,
        new_suffix: str = '',
        put_front: bool = False,        
) -> Path:
    if put_front:
        return Path(f"{tag}_{file.stem}{new_suffix if new_suffix else file.suffix}")
    else:
        return Path(f"{file.stem}_{tag}{new_suffix if new_suffix else file.suffix}")

def transfer_tex_files(
        latex_file: Path,
        files_to: Path,
        move_or_copy: str
):
    logger.debug(
        f"the latex_file is {latex_file}\n"
        f"files_to is {files_to}"
    )
    if latex_file.parent == files_to:
        logger.debug(
            "No need to transfer files; they are already in the cwd"
        )
        return
    
    tex_dot_star_files = [x for x in latex_file.parent.glob(f'{latex_file.stem}.*')]
    for x in tex_dot_star_files:
        match move_or_copy:
            case 'mv':
                x.move_into(files_to)
            case 'cp':
                x.copy_into(files_to)
            case _:
                raise RuntimeError(
                    f"Could not transfer TeX files: "
                    f"unrecognized action '{move_or_copy}'; exiting"
                )

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

def exchangeExtension(file: Path, extension: str) -> Path:
    no_extension = file.parent / file.stem
    return Path(f"{no_extension}.{extension}")

def compile_tex(
        latex_file: Path,
        compiler: str,
        *other_compile_options,
) -> subprocess.CompletedProcess:
    """Compile .tex file with provided compiler"""
    before_comp_time = datetime.now()
    
    result = None
    latex_file_dir = latex_file.parent
    
    num_runs, encoding, compile_options = COMPILER_INFO.get(
        compiler,
        (2, 'latin-1', ['--interaction=nonstopmode'])
    )
        
    command = [compiler, *compile_options, *other_compile_options, latex_file.name]    
    for i in range(num_runs):
        logger.info(
            f"Running {compiler} on {latex_file} "
            f"(pass {i+1}/{num_runs})..."
        )
        logger.debug(f"I.e., {' '.join(command)}")        
        result = subprocess.run(
            command,
            cwd=latex_file_dir,
            capture_output=True, # see result.stdout, result.stderr
            text=True,
            encoding=encoding,
            check=True, # raises subprocess.CalledProcessError
        )

    as_pdf = exchangeExtension(latex_file, 'pdf')
    if as_pdf.exists():
        pdf_modtime = datetime.fromtimestamp(as_pdf.stat().st_mtime)
        # if we already have a .pdf and it's modification is after compilation we'll use it        
        if before_comp_time < pdf_modtime:
            return result

    as_dvi = exchangeExtension(latex_file, 'dvi')
            
    if not as_dvi.exists():
        raise FileNotFoundError(f"Could not find {as_pdf} or {as_dvi} after compiling '{latex_file}'")

    pubprint_command = ['pubprint', '-pdf', '-o', as_pdf.name, as_dvi.name]
    logger.info(f"Running `{' '.join(pubprint_command)}`...")
    process = subprocess.run(
        pubprint_command,
        cwd=latex_file_dir,
        capture_output=True,
        text=True,
        check=True,
    )
            
    if not as_pdf.exists():
        raise FileNotFoundError(f"pubprint returned zero but it's expected output file doesn't exist: {as_pdf}")
            
    return result

def run_diff_pdf(
        pdf_1: Path,
        pdf_2: Path,
        cwd: Path,
        per_page_tol: int = DIFFPDF_PER_PAGE_PIXEL_TOLERANCE
) -> tuple[subprocess.CompletedProcess, Path]:
    
    diff_fname = f'diff_{pdf_1.stem}_{pdf_2.stem}.pdf'

    diffpdf_command = [
        'diff-pdf',
        f'--per-page-pixel-tolerance={per_page_tol}',
        f'--dpi={DIFF_PDF_DPI}',
        '--skip-identical',
        '--grayscale',
        '--mark-differences',
        '--verbose',
        f'--output-diff={diff_fname}',
        pdf_1.name,
        pdf_2.name
    ]
    
    logger.info(f"Running `{' '.join(diffpdf_command)}`...")

    try:
        result = subprocess.run(
            diffpdf_command,
            cwd=cwd,
            check=True,
        )
    except FileNotFoundError as e:
        logger.critical(
            "It appears diff-pdf is not installed. "
            "It is a dependency of this program. For installation "
            "instructions, go to https://vslavik.github.io/diff-pdf/"
        )
        raise e
    except subprocess.CalledProcessError as e:
        logger.critical(
            f"{pdf_1} and {pdf_2} are not identical. "
            f"See {Path(cwd) / diff_fname}"
        )
        raise e
        
    return result, Path(diff_fname)
    
def delete_intermediate_latex(latex_file: Path):
    body = latex_file.stem
    for extension in INTERMEDIATE_EXTENSIONS_TO_DELETE:
        to_delete = Path(body + extension)
        if to_delete.exists():
            logger.debug(f"Deleted {to_delete}")
            to_delete.unlink()
            
def replaceNewlines(s: str) -> str:
    return re.sub(r'[\n\r]', r' ', s)

def backslashEscape(s: str) -> str:
    return s.replace('\\', r'\\')

def UnicodeToTeX(s: str) -> str:
    return ''.join(
        UNICODE2TEX.get(char, char)
        for char in s
    )

def compile_validate_clean_replace(
        latex_file1: Path,
        latex_file2: Path,
        cwd: Path,
        compile_first: bool=False,
        **opt
):
    # no point in compiling first if not validating
    if opt['validate'] and compile_first: 
        process1 = compile_tex(latex_file1, opt['compiler'])
        
    if opt['validate']:
        process2 = compile_tex(latex_file2, opt['compiler'])

    pdf_1 = pdf_name(latex_file1)
    pdf_2 = pdf_name(latex_file2)

    second_is_auto = latex_file2.stem.endswith(AUTO_TAG)

    if opt['validate'] and not second_is_auto:
        process3, diff_fname = run_diff_pdf(
            pdf_1,
            pdf_2,
            cwd,
            per_page_tol=0,
        )
        logger.info(f"{pdf_1} and {pdf_2} are identical")
    else:
        diff_fname = None
        reason_no_diff = "expected differences" if second_is_auto else "--no-validate"
        logger.info(f"Did not compare {pdf_1} and {pdf_2} ({reason_no_diff})")

    if opt['clean']:
        logger.info("Deleting intermediate files.")
        if diff_fname is not None:
            diff_fname.unlink()
        delete_intermediate_latex(latex_file1)
        delete_intermediate_latex(latex_file2)

    # don't replace _inlined if planning to replace with _autocorrected        
    should_not_overwrite_despite_replace = (
        latex_file2.stem.endswith(INLINED_TAG) and
        opt['auto']
    ) 
    if should_not_overwrite_despite_replace:
        return

    if opt['replace']:
        latex_file2.move(latex_file1)
        logger.info(f"{latex_file1} overwritten by {latex_file2}")
        
def plural(num: int):
    return 's' if num > 1 else ''

def fromRoman(roman: str) -> int:
    """converts roman numeral to integer"""
    numerals = roman.upper()
    roman_to_int = {
        "I": 1,
        "V": 5,
        "X": 10,
        "L": 50,
        "C": 100,
        "D": 500,
        "M": 1000,
    }
    total = 0
    prev = 0

    for letter in reversed(numerals):
        curr = roman_to_int[letter]
        if curr >= prev:
            total += curr
        else:
            total -= curr
        prev = curr
    if total < 1 or total > MAX_ROMAN:
        return -1
    else:
        return total
