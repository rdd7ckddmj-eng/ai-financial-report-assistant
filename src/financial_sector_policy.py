"""Explicit financial-issuer identification; no inference from incidental prose."""
import re

SPECIAL_FINANCIAL_TEMPLATES = frozenset({
    'securities_group_parent_yuan_v1', 'bank_signed_million_v1', 'insurance_unsupported_v1', 'securities_unsupported_v1',
})


def is_special_financial_template(template):
    return template in SPECIAL_FINANCIAL_TEMPLATES


def unsupported_issuer_template(company, pages):
    name = re.sub(r'\s+', '', str(company.get('name', '')))
    if len(name) < 3 or name == '待核验公司':
        return None
    front = re.sub(r'\s+', '', '\n'.join(text for _, text in pages[:10]))
    # Bind the issuer's supplied name to its legal name. Mentioning a broker or
    # insurance product in another company's report must not classify it.
    if '证券' in name and re.search(re.escape(name)+r'(?:股份)?有限公司', front):
        return 'securities_unsupported_v1'
    if re.search(re.escape(name)+r'(?:保险)?(?:[（(]集团[）)])?(?:股份)?有限公司', front) and (
        '保险' in name or re.search(re.escape(name)+r'保险(?:[（(]集团[）)])?(?:股份)?有限公司', front)
    ):
        return 'insurance_unsupported_v1'
    return None
