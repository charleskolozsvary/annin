# Changelog
All notable changes to this project will be documented in this file (since version 0.12.0).

## [0.14.1](https://github.com/charleskolozsvary/tex-pdf-edits/commit/87934933d51f901e6225fe2b59d2518ab8b500ac) (2026-05-07)
### Bug Fixes
- Added file existence checks for positional arguments ([main.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/87934933d51f901e6225fe2b59d2518ab8b500ac#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758))
- Fixed crash caused by incorrect return value in default case of `applySourceOffset()` ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/87934933d51f901e6225fe2b59d2518ab8b500ac#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

## [0.14.0](https://github.com/charleskolozsvary/tex-pdf-edits/commit/3df9af5e7666a4fda4bae4ac02ba3b373c04311e) (2026-05-07)
### Features
- `corrinline`: added `--source-start-page`option to resync the annotated PDF and the source if their pages are not already one-to-one. See [README.md](./README.md) for further details. ([corr.py, marktex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/3df9af5e7666a4fda4bae4ac02ba3b373c04311e#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

## [0.13.9](https://github.com/charleskolozsvary/tex-pdf-edits/commit/9cfc37f553ba41792b3ebab66b1f69cdb5dbc9ae) (2026-04-14)
### Features
- The autocorrection heuristic was updated so that a unique match must include at least three total characters (from the selected text and what is to the left or right of it). This was done to reduce autocorrect false positives for single character corrections if the LaTeX snippet did not contain the selection text. ([modifytex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/9cfc37f553ba41792b3ebab66b1f69cdb5dbc9ae#diff-ccd051762c8d0d9e1780e47e5453f3072ee1eb805bfb56c4c87b8e119bb4c848))

## [0.13.8](https://github.com/charleskolozsvary/tex-pdf-edits/commit/f6e786964e0477b3cea34f85881fdd2424a13219) (2026-04-04)
### Features
- Improved strictly geometric box sorting in `rectangleToLatex()` fallback when no `tex_word_boxes` are intersected ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/f6e786964e0477b3cea34f85881fdd2424a13219#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

## [0.13.7](https://github.com/charleskolozsvary/tex-pdf-edits/commit/86efa5af2945299a995e7eb025ec8aa1f6719309) (2026-04-04)
### Features
- `corrinline` now writes its program log to a file ([main.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/86efa5af2945299a995e7eb025ec8aa1f6719309#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758))

### Bug Fixes
- added `continue` to exception in `getEnunciations()` ([marktex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/86efa5af2945299a995e7eb025ec8aa1f6719309#diff-fe2186edfd9be409ce6bb28250628955aed81f0f81a9301e1b72ad4efa589471))

## [0.13.6](https://github.com/charleskolozsvary/tex-pdf-edits/commit/fa754e35266045a7e0d10a7f3cf7e72a10d9a91c) (2026-04-02)
### Features
- All command line comment formats are now supported along with their removal with `--delete-comments` ([formatcomm.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/fa754e35266045a7e0d10a7f3cf7e72a10d9a91c#diff-20f13c668a1d29a77ac42ec65a8692371eeb2491c8bfb66d3c5713da23a54014))
- Added `--version` option to display program version ([main.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/fa754e35266045a7e0d10a7f3cf7e72a10d9a91c#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758))

### Bug Fixes
- Changed snippet merge condition in `groupOverlapping()` from `start < curr_end` to `start <= curr_end` to avoid different corrections starting and ending at the same position ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/fa754e35266045a7e0d10a7f3cf7e72a10d9a91c#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436)) and updated inlining of corrections to source accordingly ([modifytex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/fa754e35266045a7e0d10a7f3cf7e72a10d9a91c#diff-ccd051762c8d0d9e1780e47e5453f3072ee1eb805bfb56c4c87b8e119bb4c848))

## [0.13.5](https://github.com/charleskolozsvary/tex-pdf-edits/commit/057e0a6fa8e02a1bedfcbd886e8219c238bbe040) (2026-04-01)
### Features
- AMS-specific: geometric adjustment of bugged annotation bounding boxes is now supported for the STIX font ([extractanns.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/057e0a6fa8e02a1bedfcbd886e8219c238bbe040#diff-e339d74da60e0ed06ea1977c9b0b4608dce1b139ba3f8b6b06c068684aaadbfb))

### Bug Fixes
- Annotation comment text now sanitized (before only selection text for autocorrections) ([corr.py, formatcomm.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/057e0a6fa8e02a1bedfcbd886e8219c238bbe040#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

## [0.13.4](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d59f1a4da80015dc1d894846edc40d2f86a81c08) (2026-03-29)
### Features
- Sped up annotation selection text generation with `pageGetTextClipRect`---previously iterated through entire page char list for every annotation ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d59f1a4da80015dc1d894846edc40d2f86a81c08#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))
- Added a few Unicode to LaTeX character mappings for math symbols ([utils.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d59f1a4da80015dc1d894846edc40d2f86a81c08#diff-5a5367671844256a2cbe688a3bbf6dc301f708f05c96aa12b866e4dbbc7cfb9a))
- Removed minimum adjacent char distance criterion in `categorizeMarkIDs` ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d59f1a4da80015dc1d894846edc40d2f86a81c08#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

### Bug Fixes
- Corrected typo in `categorizeMarkIDs` ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d59f1a4da80015dc1d894846edc40d2f86a81c08#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

## [0.13.3](https://github.com/charleskolozsvary/tex-pdf-edits/commit/a148ac75242cde9863ef84c4203e26d353769b1e) (2026-03-29)
### Features
- Updated `rectangleToLaTeX()` fallback when no `tex_word_boxes` are intersected ([corr.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/a148ac75242cde9863ef84c4203e26d353769b1e#diff-76722a2e0598cec992c3f2be48a7e90fd43d2b7e2e8d545dde39e4dfa4577436))

## [0.13.2](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d001d0f29d0346e602d5fa9ee10c4cb5b5e002e0) (2026-03-25)
### Features
- updated autocorrect method for caret annotations; they now mostly behave the same way as replace and strikeout ([modifytex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d001d0f29d0346e602d5fa9ee10c4cb5b5e002e0#diff-ccd051762c8d0d9e1780e47e5453f3072ee1eb805bfb56c4c87b8e119bb4c848))

## [0.13.1](https://github.com/charleskolozsvary/tex-pdf-edits/commit/0d53ef313c0bb82abba254d16373ce0f718c5923) (2026-03-24)
### Bug Fixes
- resolved `--delete-comments` issue by removing extra opening and closing comment ids from `Reply:` comments ([formatcomm.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/0d53ef313c0bb82abba254d16373ce0f718c5923#diff-20f13c668a1d29a77ac42ec65a8692371eeb2491c8bfb66d3c5713da23a54014))
- added "edition" to list of `\bib` keys which cannot be marked ([marktex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/0d53ef313c0bb82abba254d16373ce0f718c5923#diff-fe2186edfd9be409ce6bb28250628955aed81f0f81a9301e1b72ad4efa589471))

## [0.13.0](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d89f1e3d94ea675ddb0c79915522827ed8163adc) (2026-03-24)
### Features
- Greatly expanded Unicode to LaTeX character mapping ([utils.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758R149))
- Added tentative `--delete-comments` option to remove inlined correction comments ([formatcomm.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d89f1e3d94ea675ddb0c79915522827ed8163adc#diff-20f13c668a1d29a77ac42ec65a8692371eeb2491c8bfb66d3c5713da23a54014))

## [0.12.0](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef) (2026-03-23)
### Features
- Correct selection text is generated from multiline PDF annotations ([extractanns.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef#diff-e339d74da60e0ed06ea1977c9b0b4608dce1b139ba3f8b6b06c068684aaadbfb))
- Updated autocorrection heuristic ([modifytex.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef#diff-ccd051762c8d0d9e1780e47e5453f3072ee1eb805bfb56c4c87b8e119bb4c848R285))
- Added a few UTF to LaTeX character mappings ([utils.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef#diff-5a5367671844256a2cbe688a3bbf6dc301f708f05c96aa12b866e4dbbc7cfb9aR33))
- Added `--comment-format` option to choose inlined correction comment format ([main.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758R149))
- Added `--extra-mark-envs` option to specify additional marked environments ([main.py](https://github.com/charleskolozsvary/tex-pdf-edits/commit/d5c978ddb9a337204cef4e37266420aabdddf7ef#diff-f5d4255ff46dd480d9c9f54ed5ca8d1ecb3375f9e7a5dd3a0ba36ebf12402758R149))

