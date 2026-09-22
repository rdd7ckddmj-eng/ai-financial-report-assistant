"""Normalize only horizontal whitespace inside one parenthesized number."""
import re


def normalize_numeric_parentheses(text):
    # Do not join lines or adjacent values: '(1 2)' and '(1\n)' stay unchanged.
    return re.sub(r'([（(])[ \t\xa0]*([-−－]?\d[\d,，]*(?:\.\d+)?)[ \t\xa0]*([）)])',
                  r'\1\2\3', text)
