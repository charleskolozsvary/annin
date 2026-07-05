import logging
logger = logging.getLogger(__name__)
import re
import subprocess

class SynctexOut:
    def __init__(self, output: str, page: str, x: str, y: str):
        self.output = output
        # SyncTeX page is 1-based and pymupdf uses 0-based
        self.page = int(page) - 1 
        self.x = float(x)
        self.y = float(y)
        if self.page < 0:
            raise ValueError(f"page less than 0: page == {self.page}")
        return
    def __str__(self):
        return (
            f'SynctexOut('
            f'output: {self.output}, '
            f'page: {self.page}, '
            f'x: {self.x}, '
            f'y: {self.y})'
        )
    def __repr__(self):
        return str(self)

def run_synctex_view(
        line: int,
        input: Path,
        output: Path,
) -> str:
    command = [
        'synctex',
        'view',
        '-i',
        f'{line}:0:{input.name}',
        '-o',
        f'{output.name}',
    ]
    # logger.debug(' '.join(command))
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout

def parse_synctex_view(
        output: str,
) -> list[SynctexOut]:
    result = re.search(
        r'^SyncTeX result begin(?P<res>.*?)^SyncTeX result end',
        output,
        flags = re.MULTILINE | re.DOTALL,
    )
    if result is None:
        # logger.debug(output)
        raise RuntimeError("Could not find SyncTeX result")
    result = result.group('res')
    fields_regex = (
        r'^Output:(?P<output>.*?)$\n'
        r'^Page:(?P<page>.*?)$\n'
        r'x:(?P<x>.*?)$\n'
        r'y:(?P<y>.*?)$\n'
    )
    synctex_outs = []

    while result:
        fields = re.search(
            fields_regex,
            result,
            flags = re.MULTILINE,
        )
        if fields is None:
            break
        output, page, x, y = (
            fields.group('output'),
            fields.group('page'),
            fields.group('x'),
            fields.group('y'),
        )        
        try:
            synctex_outs.append(SynctexOut(output, page, x, y))
        except ValueError as e:
            logger.error(f"Could not read SyncTeX output: {e}")
            
        _, last_field_end = fields.span('y')
        result = result[last_field_end:]
        
    if not synctex_outs:
        raise RuntimeError("SyncTeX result empty")
    return synctex_outs
