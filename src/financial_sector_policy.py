"""Explicit financial-issuer identification; no inference from incidental prose."""
import re
from src.insurance_group_statement_extractor import TEMPLATES

INSURANCE_ISSUERS = {
    '601318': ('中国平安', r'中国平安保险[（(]集团[）)]股份有限公司'),
    '601319': ('中国人保', r'中国人民保险集团股份有限公司'),
    '601601': ('中国太保', r'中国太平洋保险[（(]集团[）)]股份有限公司'),
    '601336': ('新华保险', r'新华人寿保险股份有限公司'),
    '601628': ('中国人寿', r'中国人寿保险股份有限公司'),
}


def matches_known_insurer(company, pages):
    issuer = INSURANCE_ISSUERS.get(str(company.get('code', '')))
    front = re.sub(r'\s+', '', '\n'.join(t for _, t in pages[:10]))
    return bool(issuer and company.get('name') == issuer[0] and re.search(issuer[1], front))

SECURITIES_REVENUE_TEMPLATES = frozenset({'securities_group_parent_yuan_v1', 'securities_cms_separate_yuan_v1'})

SPECIAL_FINANCIAL_TEMPLATES = frozenset(TEMPLATES.values()) | SECURITIES_REVENUE_TEMPLATES | frozenset({
    'insurance_chinalife_million_v1', 'insurance_signed_million_v1', 'securities_group_parent_yuan_v1', 'bank_signed_million_v1', 'insurance_unsupported_v1', 'securities_unsupported_v1',
})


def is_special_financial_template(template):
    return template in SPECIAL_FINANCIAL_TEMPLATES


def unsupported_issuer_template(company, pages):
    name = re.sub(r'\s+', '', str(company.get('name', '')))
    # Known broker codes must never fall back to ordinary-company ratios, even
    # when their image cover delays the machine-readable legal-name fields.
    if str(company.get('code', '')) in {'601688', '600999'}:
        return 'securities_unsupported_v1'
    if len(name) < 3 or name == '待核验公司':
        return None
    front = re.sub(r'\s+', '', '\n'.join(text for _, text in pages[:10]))
    # A known listed insurer remains a financial issuer even when a cover's
    # legal-name logo is an image. This only disables general-company parsing;
    # Enabling a new extractor still requires matches_known_insurer.
    issuer = INSURANCE_ISSUERS.get(str(company.get('code', '')))
    if issuer and name == issuer[0]:
        return 'insurance_unsupported_v1'
    # Bind the issuer's supplied name to its legal name. Mentioning a broker or
    # insurance product in another company's report must not classify it.
    if '证券' in name and re.search(re.escape(name)+r'(?:股份)?有限公司', front):
        return 'securities_unsupported_v1'
    if re.search(re.escape(name)+r'(?:保险)?(?:[（(]集团[）)])?(?:股份)?有限公司', front) and (
        '保险' in name or re.search(re.escape(name)+r'保险(?:[（(]集团[）)])?(?:股份)?有限公司', front)
    ):
        return 'insurance_unsupported_v1'
    return None
