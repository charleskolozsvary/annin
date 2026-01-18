import difflib

def normalize_whitespace(s: str) -> str:
    return ' '.join(s.split())

def largest_common_substring(A, B):
    matcher = difflib.SequenceMatcher(None, A, B)
    match = max(matcher.get_matching_blocks(), key=lambda x: x.size)
    return A[match.a : match.a + match.size]

A = "This is a short sentence with some words."
B = """
Here is a much longer document spanning multiple pages.
It contains some words and phrases, including a short sentence




with some words embedded in it.
"""

L = largest_common_substring(A, B)
print(L)

A = normalize_whitespace(A)
B = normalize_whitespace(B)


L = largest_common_substring(A, B)
print(L)


C = r"NSF grant No. 329532MF."
D = r"The author gratefully acknowledges support from NSF grant No.\ 329532MF\@."

print(largest_common_substring(C, D))



