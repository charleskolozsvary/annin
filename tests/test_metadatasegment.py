from pathlib import Path
import logging
import argparse

from pylatexenc.latexwalker import LatexWalker, LatexEnvironmentNode, LatexMacroNode, LatexMathNode, LatexCharsNode, LatexGroupNode, LatexCommentNode
from pylatexenc.macrospec import LatexContextDb, MacroSpec, EnvironmentSpec

from texpdfedits.segmentsource import sourceAsString, RECOGNIZED_CSNAMES, getPreambleAndDocument, getEnunciations, getMetadataAndSelectEnvironments

def testPhase1(tex_filename: str):
    tex_filename = Path(tex_filename)
    
    tex_str = sourceAsString(tex_filename)
    latex_context = LatexContextDb()

    macro_specs = [MacroSpec(csname, args_parser=args_format) for csname, args_format in RECOGNIZED_CSNAMES.items()]
    
    latex_context.add_context_category('more-macros',macros=macro_specs)
    
    nodelist, _, _ = LatexWalker(tex_str, latex_context=latex_context).get_latex_nodes(pos=0)
    
    if ''.join([node.latex_verbatim() for node in nodelist]) != tex_str:
        logging.error(f"Verbatim string tex source was not preserved after LatexWalker parsing. The parser has likely failed. Exiting unsuccessfully.")
        sys.exit(1)
           
    preamble_nodes, document_node = getPreambleAndDocument(nodelist)

    ## Let's get metadata here >>>
    enunciation_names, enunciation_source = getEnunciations(preamble_nodes)
    metadata, metadata_source, environments = getMetadataAndSelectEnvironments(preamble_nodes, document_node)

    print(f"\nEnunciation names: \n{enunciation_names}")
    print(f"\nEnunciation source: \n```\n{enunciation_source}\n```")
    print("\nMetadata: \n" + '\n'.join([f"{name}: {meta_list}" for name, meta_list in metadata.items()]))
    print(f"\nMetadata_source: \n```\n{metadata_source}\n```")
    print("\nEnvironments: \n" + '\n'.join([f"{name}: {env_list}" for name, env_list in environments.items()]))
    
    return 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')

    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')    
    
    testPhase1(args.filename)
