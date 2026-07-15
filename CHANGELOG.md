# Changelog
All notable changes to this project will be documented in this file (since version 0.12.0 of `annin`).

## `vercorr` [0.1.0](https://github.com/charleskolozsvary/annin/commit/ba3e1caf839e3a49da3aab88edfef93bfafe2599) (2026-07-15)
### Features
- A GUI application that displays before/after images for each annotation to streamline correction verification
- A panel of annotations appears the right: you can navigate to each annotation and change it's checkmark or status like in Adobe Acrobat

## `annin` [0.17.0](https://github.com/charleskolozsvary/annin/commit/15c10082da3ccfc33b1f8376622fef1a9e743be2) (2026-07-15)
### Features
- Write status and checkmarks from the annotated PDF if they are initialized [aa89d84](https://github.com/charleskolozsvary/annin/commit/aa89d8440d3c76e6c30bf716b5ba6d265eb854fa)

## `annin` [0.16.2](https://github.com/charleskolozsvary/annin/commit/a5175dfe86d430f9e85e65515a9b181e31c747d2) (2026-07-13)
### Bug Fixes
- Fixed svn error handling [a5175df](https://github.com/charleskolozsvary/annin/commit/a5175dfe86d430f9e85e65515a9b181e31c747d2)
- Fixed sanitization of PDF comment text (replaced newlines) used when performing autocorrections to prevent inconsistent line endings [a5175df](https://github.com/charleskolozsvary/annin/commit/a5175dfe86d430f9e85e65515a9b181e31c747d2)

## `annin` [0.16.1](https://github.com/charleskolozsvary/annin/commit/559f8cf147aca54737ec35aa47cdea445b98029d) (2026-06-26)
### Bug Fixes
- Fixed `--no-svn --delete-comments` optional argument combination which would still svn commit [a4d6b84](https://github.com/charleskolozsvary/annin/commit/a4d6b84f2b9aa43c9faf6b27f91b01cb2ed9e4b5)
- Fixed greedy svn commit of `latex_file` directory [a4d6b84](https://github.com/charleskolozsvary/annin/commit/a4d6b84f2b9aa43c9faf6b27f91b01cb2ed9e4b5)

## `annin` [0.16.0](https://github.com/charleskolozsvary/annin/commit/1a009115b30007890baf4eb39c6248f589ae0129) (2026-06-26)
### Features
- New option `--svn`: performs svn operations (default=True) [c0dfb22](https://github.com/charleskolozsvary/annin/commit/c0dfb22f86dc349aae337e47ae9e598a4179cd98)
- New option `--no-validate`: does not check for visual differences (default=False) [c0dfb22](https://github.com/charleskolozsvary/annin/commit/c0dfb22f86dc349aae337e47ae9e598a4179cd98)
- Updated option `--replace`: latex_file is replaced by _inlined or _autocorrected (default=True) [c0dfb22](https://github.com/charleskolozsvary/annin/commit/c0dfb22f86dc349aae337e47ae9e598a4179cd98)

## `annin` [0.15.0](https://github.com/charleskolozsvary/annin/commit/f9e1ff3aca3b3263486019b610e113f4f8a266fc) (2026-06-20)
### Features
- Script name changed from `corrinline` to `annin` (after updating, rerun `./install.sh` like during original installation) [3f782f8](https://github.com/charleskolozsvary/annin/commit/3f782f84f91e73e184432b701569f3514ec77e5c)
- Supports roman numeral page numbering (e.g. in books) as long as PDF label metadata is accurate [780447d](https://github.com/charleskolozsvary/annin/commit/780447d8b7faf6bb4dd794028e5f17c1e425985a)
- Updated annotation comment formatting: `Selection: "Or <Hightlight>something</Hightlight>"` to `Highlight: "Or <SEL>something</SEL>"` [be96c65](https://github.com/charleskolozsvary/annin/commit/be96c650bec55bc52c7a26637345bbf872b34a5c)
- Greatly improved snippet isolation for annotations in or near `\bib` commands [2d5637b](https://github.com/charleskolozsvary/annin/commit/2d5637bde80287f6fce5dd8c257e8dc02ef4a671)
- Improved marking (and hence snippet identification) for characters after accents [d89a177](https://github.com/charleskolozsvary/annin/commit/d89a177be3e4680af35e8951751f99be7865c4e5)

### Bug Fixes
- Discrepancies between `prdlatex -pdf` and `prdlatex` -> `pubprint` now resolved by running `pubprint` by default for any compiler that doesn't generate a PDF [b4efce8](https://github.com/charleskolozsvary/annin/commit/b4efce8f390bac0cf01ebd8814f7959e71ee87c4)
- `annin -dc latex_file` now works as intended (you don't need to supply `pdf_file` if just deleting comments) [e13af39](https://github.com/charleskolozsvary/annin/commit/e13af39257adc1a52753b13c0152d38ab68838d0)
- Fixed `re.subn` replacement string bug if interpolated text in `\1{left}` started with digit (`\1` and the like to `\g<1>`) [c3b3628](https://github.com/charleskolozsvary/annin/commit/c3b36288d59fbfbff73253ee0a3c47763a1f4388)

## `annin` [0.14.3](https://github.com/charleskolozsvary/tex-pdf-edits/commit/144f7b16bdb89425eefd84c11ea1864c5223b4bc) (2026-05-12)
### Features
- Removed "not for COMP" heuristic annotation filtering. It is better to insert all the annotations from the PDF into the source. [extractanns.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/144f7b16bdb89425eefd84c11ea1864c5223b4bc#diff-e339d74da60e0ed06ea1977c9b0b4608dce1b139ba3f8b6b06c068684aaadbfb)
- Updated filter for replacement or insertion text which is likely not literal (e.g. to prevent inserting "the au: okay?") [modifytex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/144f7b16bdb89425eefd84c11ea1864c5223b4bc#diff-ccd051762c8d0d9e1780e47e5453f3072ee1eb805bfb56c4c87b8e119bb4c848)
- Added short versions of command line options and renamed `--source-start-page` to `--tex-start` [main.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/144f7b16bdb89425eefd84c11ea1864c5223b4bc#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758)
- Removed check mark from status brackets for autocorrected edits. Now they are only indicated by `(AUTOCORRECTED)` [formatcomm.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/144f7b16bdb89425eefd84c11ea1864c5223b4bc#diff-20f13c668a1d29a77ac42ec65a8692371eeb2491c8bfb66d3c5713da23a54014)

## `annin` [0.14.2](https://github.com/charleskolozsvary/tex-pdf-edits/commit/366dd4f3a455a1b64fa26242583199a7764a81a8) (2026-05-08)
### Bug Fixes
- Corrected marking behavior after accent macros to prevent failure cases like those shown in [accents.tex](./tests/fixtures/accents.tex) ([marktex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/366dd4f3a455a1b64fa26242583199a7764a81a8#diff-fe2186edfd9be409ce6bb28250628955aed81f0f81a9301e1b72ad4efa589471))

## `annin` [0.14.1](https://github.com/charleskolozsvary/tex-pdf-edits/commit/87934933d51f901e6225fe2b59d2518ab8b500ac) (2026-05-07)
### Bug Fixes
- Added file existence checks for positional arguments ([main.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/87934933d51f901e6225fe2b59d2518ab8b500ac#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758))
- Fixed crash caused by incorrect return value in default case of `applySourceOffset()` ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/87934933d51f901e6225fe2b59d2518ab8b500ac#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

## `annin` [0.14.0](https://github.com/charleskolozsvary/tex-pdf-edits/commit/3df9af5e7666a4fda4bae4ac02ba3b373c04311e) (2026-05-07)
### Features
- `corrinline`: added `--source-start-page`option to resync the annotated PDF and the source if their pages are not already one-to-one. See [README.md](./README.md) for further details. ([corr.py, marktex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/3df9af5e7666a4fda4bae4ac02ba3b373c04311e#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

## `annin` [0.13.9](https://github.com/charleskolozsvary/tex-pdf-edits/commit/9cfc37f553ba41792b3ebab66b1f69cdb5dbc9ae) (2026-04-14)
### Features
- The autocorrection heuristic was updated so that a unique match must include at least three total characters (from the selected text and what is to the left or right of it). This was done to reduce autocorrect false positives for single character corrections if the LaTeX snippet did not contain the selection text. ([modifytex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/9cfc37f553ba41792b3ebab66b1f69cdb5dbc9ae#diff-ccd051762c8d0d9e1780e47e5453f3072ee1eb805bfb56c4c87b8e119bb4c848))

## `annin` [0.13.8](https://github.com/charleskolozsvary/tex-pdf-edits/commit/f6e786964e0477b3cea34f85881fdd2424a13219) (2026-04-04)
### Features
- Improved strictly geometric box sorting in `rectangleToLatex()` fallback when no `tex_word_boxes` are intersected ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/f6e786964e0477b3cea34f85881fdd2424a13219#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

## `annin` [0.13.7](https://github.com/charleskolozsvary/tex-pdf-edits/commit/86efa5af2945299a995e7eb025ec8aa1f6719309) (2026-04-04)
### Features
- `corrinline` now writes its program log to a file ([main.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/86efa5af2945299a995e7eb025ec8aa1f6719309#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758))

### Bug Fixes
- added `continue` to exception in `getEnunciations()` ([marktex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/86efa5af2945299a995e7eb025ec8aa1f6719309#diff-fe2186edfd9be409ce6bb28250628955aed81f0f81a9301e1b72ad4efa589471))

## `annin` [0.13.6](https://github.com/charleskolozsvary/tex-pdf-edits/commit/fa754e35266045a7e0d10a7f3cf7e72a10d9a91c) (2026-04-02)
### Features
- All command line comment formats are now supported along with their removal with `--delete-comments` ([formatcomm.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/fa754e35266045a7e0d10a7f3cf7e72a10d9a91c#diff-20f13c668a1d29a77ac42ec65a8692371eeb2491c8bfb66d3c5713da23a54014))
- Added `--version` option to display program version ([main.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/fa754e35266045a7e0d10a7f3cf7e72a10d9a91c#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758))

### Bug Fixes
- Changed snippet merge condition in `groupOverlapping()` from `start < curr_end` to `start <= curr_end` to avoid different corrections starting and ending at the same position ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/fa754e35266045a7e0d10a7f3cf7e72a10d9a91c#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436)) and updated inlining of corrections to source accordingly ([modifytex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/fa754e35266045a7e0d10a7f3cf7e72a10d9a91c#diff-ccd051762c8d0d9e1780e47e5453f3072ee1eb805bfb56c4c87b8e119bb4c848))

## `annin` [0.13.5](https://github.com/charleskolozsvary/tex-pdf-edits/commit/057e0a6fa8e02a1bedfcbd886e8219c238bbe040) (2026-04-01)
### Features
- AMS-specific: geometric adjustment of bugged annotation bounding boxes is now supported for the STIX font ([extractanns.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/057e0a6fa8e02a1bedfcbd886e8219c238bbe040#diff-e339d74da60e0ed06ea1977c9b0b4608dce1b139ba3f8b6b06c068684aaadbfb))

### Bug Fixes
- Annotation comment text now sanitized (before only selection text for autocorrections) ([corr.py, formatcomm.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/057e0a6fa8e02a1bedfcbd886e8219c238bbe040#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

## `annin` [0.13.4](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d59f1a4da80015dc1d894846edc40d2f86a81c08) (2026-03-29)
### Features
- Sped up annotation selection text generation with `pageGetTextClipRect`---previously iterated through entire page char list for every annotation ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d59f1a4da80015dc1d894846edc40d2f86a81c08#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))
- Added a few Unicode to LaTeX character mappings for math symbols ([utils.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d59f1a4da80015dc1d894846edc40d2f86a81c08#diff-5a5367671844256a2cbe688a3bbf6dc301f708f05c96aa12b866e4dbbc7cfb9a))
- Removed minimum adjacent char distance criterion in `categorizeMarkIDs` ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d59f1a4da80015dc1d894846edc40d2f86a81c08#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

### Bug Fixes
- Corrected typo in `categorizeMarkIDs` ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d59f1a4da80015dc1d894846edc40d2f86a81c08#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

## `annin` [0.13.3](https://github.com/charleskolozsvary/tex-pdf-edits/commit/a148ac75242cde9863ef84c4203e26d353769b1e) (2026-03-29)
### Features
- Updated `rectangleToLaTeX()` fallback when no `tex_word_boxes` are intersected ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/a148ac75242cde9863ef84c4203e26d353769b1e#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

## `annin` [0.13.2](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d001d0f29d0346e602d5fa9ee10c4cb5b5e002e0) (2026-03-25)
### Features
- updated autocorrect method for caret annotations; they now mostly behave the same way as replace and strikeout ([modifytex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d001d0f29d0346e602d5fa9ee10c4cb5b5e002e0#diff-ccd051762c8d0d9e1780e47e5453f3072ee1eb805bfb56c4c87b8e119bb4c848))

## `annin` [0.13.1](https://github.com/charleskolozsvary/tex-pdf-edits/commit/0d53ef313c0bb82abba254d16373ce0f718c5923) (2026-03-24)
### Bug Fixes
- resolved `--delete-comments` issue by removing extra opening and closing comment ids from `Reply:` comments ([formatcomm.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/0d53ef313c0bb82abba254d16373ce0f718c5923#diff-20f13c668a1d29a77ac42ec65a8692371eeb2491c8bfb66d3c5713da23a54014))
- added "edition" to list of `\bib` keys which cannot be marked ([marktex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/0d53ef313c0bb82abba254d16373ce0f718c5923#diff-fe2186edfd9be409ce6bb28250628955aed81f0f81a9301e1b72ad4efa589471))

## `annin` [0.13.0](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d89f1e3d94ea675ddb0c79915522827ed8163adc) (2026-03-24)
### Features
- Greatly expanded Unicode to LaTeX character mapping ([utils.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758R149))
- Added tentative `--delete-comments` option to remove inlined correction comments ([formatcomm.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d89f1e3d94ea675ddb0c79915522827ed8163adc#diff-20f13c668a1d29a77ac42ec65a8692371eeb2491c8bfb66d3c5713da23a54014))

## `annin` [0.12.0](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef) (2026-03-23)
### Features
- Correct selection text is generated from multiline PDF annotations ([extractanns.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef#diff-e339d74da60e0ed06ea1977c9b0b4608dce1b139ba3f8b6b06c068684aaadbfb))
- Updated autocorrection heuristic ([modifytex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef#diff-ccd051762c8d0d9e1780e47e5453f3072ee1eb805bfb56c4c87b8e119bb4c848R285))
- Added a few UTF to LaTeX character mappings ([utils.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef#diff-5a5367671844256a2cbe688a3bbf6dc301f708f05c96aa12b866e4dbbc7cfb9aR33))
- Added `--comment-format` option to choose inlined correction comment format ([main.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758R149))
- Added `--extra-mark-envs` option to specify additional marked environments ([main.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758R149))

