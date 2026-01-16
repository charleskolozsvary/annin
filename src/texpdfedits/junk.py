def writePrompt(chunk: list[Correction]):
    if len(chunk) == 0:
        return chunk[0].asMarkdownPrompt()
    prompt = ''
    for i, correction in enumerate(chunk):
        prompt += f'# Correction \#{i+1}:\n{correction.asMarkdownprompt()}\n'
    return prompt

class Response:
    def __init__(self, raw_string: str, corrirt: list[Correction], model_name: str):
        self.string = raw_string
        self.corrirt = corrit
        self.model_name = model_name

        corr_keys = {corr.index: corr for corr in corrirt}

        codeblocks = []
        matches = re.finditer(r'```(\w+)\n(.*?)\n?```', self.string, re.DOTALL)

        for i, match in enumerate(matches):
            codeblocks.append({
                'language': match.group(1),
                 'code': match.group(2),
                 'start': match.start(),
                 'end': match.end()
            })

        if len(codeblocks) != len(corrit):
            logging.warning(
                f"A response from {self.model_name} returned a different number of codeblocks "
                f"{len(codeblocks)} than submitted corrections {len(corrit)}"
            )

        languages = set(block['language'] for block in codeblocks)

        if languages != {'latex'}:
            logging.warning(
                "The languages of the markdown codeblocks in response to "
                f"corrections {list(corr_keys.keys())} were not all 'latex': {languages}"
            )

        explanations = []
        for i, block in enumerate(codeblocks):
            if i == len(codeblocks)-1:
                end = -1
            else:
                end = codeblocks[i+1]['start']
            start = block['end']
            explanations.append(self.string[start:end])

        self.codeblocks = codeblocks
        self.explanations = explanations

        # wait I can't actually single prompt chunk overlapping corrections---I would need to keep those in the same chat, prompting with
        # the contactenated history of each and maybe the first prompt will include information like "The subsequent corrections all overlap
        
    def __str__(self):
        return self.string
    def __repr__(self):
        return str(self)





def getChunks(
        key_to_correction: dict[int, Correction],
        overlapping_corrections: list[list[int]],
        corridx_to_groupidx: dict[int, int],
        chunksize: int) -> dict[str, list[list[Correction]]]:
    """Could further group corrections by type or some other information in the future"""
    
    chunks = {'overlapping': [], 'standalone': []} # dict[str, list[list[Correction]]] # allows for future further categorization, too
    def makeChunks(keys, category):
        curr_chunk = []
        for k in keys:
            if len(curr_chunk) ==  chunksize:
                chunks[category].append(curr_chunk)
                curr_chunk = []
            curr_chunk.append(key_to_correction[k])
        if curr_chunk:
            chunks[category].append(curr_chunk)
            
    # chunk overlapping corrections
    for overlap in overlapping_corrections:
        makeChunks(overlap, 'overlapping')

    # chunk non-overlapping corrections
    standalone_keys = [corridx for corridx in key_to_correction if corridx not in corridx_to_groupidx]
    makeChunks(standalone_keys, 'standalone')

    return chunks



## in doCorrections
    corridx_to_groupidx = {o_cidx: idx for idx, group in enumerate(overlapping_corrections) for o_cidx in group}
    
    def updateOverlapping(corridx: int, new_source_pos: tuple[int], new_snippet: str):
        if corridx not in corridx_to_groupidx:
            return # exit early; do nothing
        overlap = overlapping_corrections[corridx_to_groupidx[corridx]]
        for o_cidx in overlap:
            key_to_correction[o_cidx].updateSnippet(new_source_pos, new_snippet)
        logging.debug(f"Updated overlap {overlap}, triggered by correction {corridx}")
