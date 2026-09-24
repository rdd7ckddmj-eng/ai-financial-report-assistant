"""Bounded recovery of native glyph text displaced by foreign-page ActualText.

Selection is structural, before any financial calculation: duplicate StructParents
and replacement spans explicitly pointing to another physical page. The default
text is retained. This supports a flat, explicit ParentTree only; ambiguous or
incomplete PDF structure does not authorize replacement text.
"""
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
import re

SCHEMA = 'pdf_actualtext_recovery_v1'
MAX_RECOVERY_PAGES = 6
MAX_PAGE_TEXT = 16000
MAX_RECOVERY_CHARACTERS = 96000
MAX_STRUCTURE_TEXT = 100000
MAX_FOREIGN_REPLACEMENTS = 160
MAX_ACTUALTEXT_CHARACTERS = 16000
_TITLES = ('合并及公司资产负债表', '合并及公司利润表', '合并及公司现金流量表',
           '合并资产负债表', '合并利润表', '合并现金流量表')
_HASH = re.compile(r'[0-9a-f]{64}')
_REASON = 'foreign_page_actualtext_structparents_collision'
_FIELDS = set('schema method reason pdf_fingerprint_sha256 report_year page_number page_xref '
              'struct_parents colliding_pages parent_tree_xref parent_array_xref foreign_replacements '
              'default_flags native_flags parser_version statement_title header_excerpt header_years '
              'original_text_sha256 native_text_sha256 original_text native_text original_excerpt native_excerpt'.split())


def _hash(text):
    return sha256(text.encode('utf-8')).hexdigest()


def _title(text):
    # Only an actual leading statement heading; a contents reference is not one.
    lines = [re.sub(r'\s+', '', line) for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    return next((title for title in _TITLES if re.fullmatch(
        re.escape(title) + r'(?:[-－—]续|[（(]续[）)])?', lines[0])), None)


def _default_title(text, foreign=None):
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or len(lines[0]) > 500:
        return None
    first = re.sub(r'\s+', '', lines[0])
    title = next((title for title in _TITLES if first.startswith(title)), None)
    if title is None or foreign is None:
        return title
    # Replacement evidence may itself contain common characters in the valid
    # heading. Remove it only from the damaged suffix after the exact title.
    suffix = first[len(title):]
    for item in foreign:
        actual = re.sub(r'\s+', '', item['actual_text'])
        if actual:
            suffix = suffix.replace(actual, '')
    return title if re.fullmatch(r'(?:[-－—]?续|[（(]续[）)])?', suffix) else None


def _header(text, report_year):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    compact = [re.sub(r'\s+', '', line) for line in lines]
    boundary = next((i for i, line in enumerate(compact) if line in
        {'流动资产', '流动负债', '一、营业收入', '一、营业总收入', '一、经营活动产生的现金流量'}), None)
    if boundary is None or not 7 <= boundary <= 13:
        return None
    header = '\n'.join(lines[:boundary])
    title = _title(text)
    if title is None or len(header) > 1600:
        return None
    balance = title.endswith('资产负债表')
    date = f'{report_year}年12月31日'
    # A matching year alone cannot turn a half-year/quarterly statement into
    # an annual one. Require the complete period and every dated column.
    if compact[1] != date + ('' if balance else '止年度'):
        return None
    if not re.fullmatch(r'[（(]除特别注明外[，,]金额单位为人民币(?:百万元|千元|万元|元)[）)]', compact[2]):
        return None
    allowed_labels = {'资产', '负债和股东权益'} if balance else {'项目'}
    if compact[3] not in allowed_labels or compact[4] != '附注':
        return None
    current = date if balance else f'{report_year}年度'
    previous = f'{report_year - 1}年12月31日' if balance else f'{report_year - 1}年度'
    expected = ([[current, '合并', previous, '合并', current, '公司', previous, '公司']]
                if title.startswith('合并及公司') else
                [[current, previous], [current, '合并', previous, '合并']])
    if compact[5:boundary] not in expected:
        return None
    return header


def _xref(document, owner, key):
    kind, value = document.xref_get_key(owner, key)
    if kind != 'xref' or not re.fullmatch(r'[1-9]\d* 0 R', value):
        return None
    return int(value.split()[0])


def _reference_array(text):
    if len(text) > MAX_STRUCTURE_TEXT or not re.fullmatch(r'\[\s*(?:[1-9]\d*\s+0\s+R\s*)+\]', text):
        return None
    refs = [int(x) for x in re.findall(r'(\d+)\s+0\s+R', text)]
    return refs if len(refs) <= 4096 else None


def derive_native_text_recovery(document, page, *, original_text, report_year,
                                pdf_fingerprint, module):
    """Return a fully evidenced native reading or None; never inspect amounts."""
    title = _default_title(original_text)
    if (not title or type(report_year) is not int or not 1990 <= report_year <= 2200
            or len(original_text) > MAX_PAGE_TEXT):
        return None
    # Optional native functionality: older/fake engines retain their default path.
    if not hasattr(module, 'TEXT_IGNORE_ACTUALTEXT') or not hasattr(document, 'xref_get_key'):
        return None
    kind, key = document.xref_get_key(page.xref, 'StructParents')
    if kind != 'int' or not re.fullmatch(r'\d+', key):
        return None
    owners = []; page_map = {}
    for index in range(document.page_count):
        other = document[index]
        page_map[other.xref] = index + 1
        if document.xref_get_key(other.xref, 'StructParents') == (kind, key):
            owners.append(dict(page_number=index + 1, page_xref=other.xref))
    if len(owners) < 2 or len(owners) > 8:
        return None
    root = _xref(document, document.pdf_catalog(), 'StructTreeRoot')
    parent = _xref(document, root, 'ParentTree') if root else None
    if not parent:
        return None
    typ, nums = document.xref_get_key(parent, 'Nums')
    if (typ != 'array' or len(nums) > MAX_STRUCTURE_TEXT or not re.fullmatch(
            r'\[\s*(?:\d+\s+[1-9]\d*\s+0\s+R\s*)+\]', nums)):
        return None
    pairs = [(int(a), int(b)) for a, b in re.findall(r'(\d+)\s+(\d+)\s+0\s+R', nums)]
    if len(pairs) > 1000 or len({k for k, _ in pairs}) != len(pairs):
        return None
    array_xref = dict(pairs).get(int(key))
    if not array_xref:
        return None
    refs = _reference_array(document.xref_object(array_xref))
    if refs is None:
        return None
    positions = defaultdict(list)
    for mcid, ref in enumerate(refs):
        positions[ref].append(mcid)
    foreign = []; actual_characters = 0
    for ref, ids in positions.items():
        typ, actual = document.xref_get_key(ref, 'ActualText')
        if typ == 'null':
            continue
        pg = _xref(document, ref, 'Pg')
        ktype, kid = document.xref_get_key(ref, 'K')
        if (ktype != 'array' or len(kid) > MAX_STRUCTURE_TEXT
                or not re.fullmatch(r'\[\s*\d{1,4}(?:\s+\d{1,4})*\s*\]', kid)):
            return None
        tokens = kid[1:-1].split()
        if len(tokens) > 4096:
            return None
        expected_ids = [int(x) for x in tokens]
        if any(x >= 4096 for x in expected_ids):
            return None
        if (typ != 'string' or not actual or len(actual) > 2000 or pg == page.xref
                or pg not in {o['page_xref'] for o in owners} or ids != expected_ids):
            return None
        actual_characters += len(actual)
        if len(foreign) >= MAX_FOREIGN_REPLACEMENTS or actual_characters > MAX_ACTUALTEXT_CHARACTERS:
            return None
        foreign.append(dict(structure_xref=ref, actual_text=actual,
            referenced_page_xref=pg, referenced_page_number=page_map[pg], marked_content_ids=ids))
    if (not foreign or len(foreign) > MAX_FOREIGN_REPLACEMENTS
            or sum(len(x['actual_text']) for x in foreign) > MAX_ACTUALTEXT_CHARACTERS
            or not any(len(x['actual_text']) >= 2 and x['actual_text'] in original_text for x in foreign)):
        return None
    if _default_title(original_text, foreign) != title:
        return None
    native_flags = module.TEXTFLAGS_TEXT | module.TEXT_IGNORE_ACTUALTEXT
    native = page.get_text('text', flags=native_flags)
    header = _header(native, report_year)
    if native == original_text or len(native) > MAX_PAGE_TEXT or _title(native) != title or header is None:
        return None
    return dict(schema=SCHEMA, method='pymupdf_ignore_actualtext', reason=_REASON,
        pdf_fingerprint_sha256=pdf_fingerprint, report_year=report_year,
        page_number=page.number + 1, page_xref=page.xref, struct_parents=int(key),
        colliding_pages=owners, parent_tree_xref=parent, parent_array_xref=array_xref,
        foreign_replacements=foreign, default_flags=module.TEXTFLAGS_TEXT,
        native_flags=native_flags, parser_version=str(module.VersionBind),
        statement_title=title, header_excerpt=header, header_years=[report_year, report_year - 1],
        original_text_sha256=_hash(original_text), native_text_sha256=_hash(native),
        original_text=original_text, native_text=native,
        original_excerpt=original_text[:1600], native_excerpt=native[:1600])


def validate_native_text_recoveries(records, *, pdf_fingerprint=None, report_year=None):
    """Validate retained evidence at downstream boundaries; return a safe copy.

    This checks identity, shape and internal integrity, not an independently
    downloaded PDF. Production source verification is performed during extraction.
    """
    def fail():
        raise ValueError('PDF原生文字恢复依据不完整或与原件、年度不一致，不能继续标准化。')
    if not isinstance(records, list) or len(records) > MAX_RECOVERY_PAGES:
        fail()
    total = 0; seen = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != _FIELDS: fail()
        if (record.get('schema') != SCHEMA or record.get('method') != 'pymupdf_ignore_actualtext'
                or record.get('reason') != _REASON): fail()
        digest = record.get('pdf_fingerprint_sha256')
        year = record.get('report_year')
        if (not isinstance(digest, str) or not _HASH.fullmatch(digest)
                or (pdf_fingerprint is not None and digest != pdf_fingerprint)
                or type(year) is not int or not 1990 <= year <= 2200
                or (report_year is not None and year != report_year)): fail()
        for key in ['page_number', 'page_xref', 'parent_tree_xref', 'parent_array_xref']:
            if type(record.get(key)) is not int or record[key] <= 0: fail()
        if (record['page_number'] > 1000 or record['page_number'] in seen
                or type(record.get('struct_parents')) is not int or record['struct_parents'] < 0): fail()
        seen.add(record['page_number'])
        if (record.get('default_flags') != 195 or record.get('native_flags') != (195 | 2048)
                or not isinstance(record.get('parser_version'), str)
                or len(record['parser_version']) > 40
                or not re.fullmatch(r'\d+\.\d+\.\d+(?:[a-zA-Z0-9.+-]*)', record['parser_version'])): fail()
        for name in ['original', 'native']:
            text = record.get(name + '_text')
            if not isinstance(text, str) or not text or len(text) > MAX_PAGE_TEXT: fail()
            total += len(text)
            if (record.get(name + '_text_sha256') != _hash(text)
                    or record.get(name + '_excerpt') != text[:1600]): fail()
        if (record['native_text'] == record['original_text']
                or _default_title(record['original_text']) != record.get('statement_title')
                or _title(record['native_text']) != record.get('statement_title')
                or record.get('statement_title') not in _TITLES
                or _header(record['native_text'], year) != record.get('header_excerpt')
                or record.get('header_excerpt') is None
                or record.get('header_years') != [year, year - 1]): fail()
        owners = record.get('colliding_pages')
        if not isinstance(owners, list) or not 2 <= len(owners) <= 8: fail()
        if any(not isinstance(o, dict) or set(o) != {'page_number', 'page_xref'}
               or type(o['page_number']) is not int or not 1 <= o['page_number'] <= 1000
               or type(o['page_xref']) is not int or o['page_xref'] <= 0 for o in owners): fail()
        if (len({o['page_number'] for o in owners}) != len(owners)
                or len({o['page_xref'] for o in owners}) != len(owners)
                or {'page_number': record['page_number'], 'page_xref': record['page_xref']} not in owners): fail()
        foreign = record.get('foreign_replacements')
        if not isinstance(foreign, list) or not 1 <= len(foreign) <= MAX_FOREIGN_REPLACEMENTS: fail()
        refs = set(); mcids = set(); actual_chars = 0
        for item in foreign:
            if not isinstance(item, dict) or set(item) != {
                    'structure_xref', 'actual_text', 'referenced_page_xref',
                    'referenced_page_number', 'marked_content_ids'}: fail()
            ref, text, ids = item.get('structure_xref'), item.get('actual_text'), item.get('marked_content_ids')
            if (type(ref) is not int or ref <= 0 or ref in refs
                    or not isinstance(text, str) or not 1 <= len(text) <= 2000
                    or not isinstance(ids, list) or not ids or len(ids) > 4096
                    or any(type(i) is not int or not 0 <= i < 4096 for i in ids)
                    or ids != sorted(set(ids)) or set(ids) & mcids): fail()
            refs.add(ref); mcids.update(ids); actual_chars += len(text)
            owner = dict(page_number=item.get('referenced_page_number'), page_xref=item.get('referenced_page_xref'))
            if (any(type(v) is not int for v in owner.values())
                    or owner not in owners or owner['page_xref'] == record['page_xref']): fail()
        if (_default_title(record['original_text'], foreign) != record['statement_title']
                or actual_chars > MAX_ACTUALTEXT_CHARACTERS or not any(len(x['actual_text']) >= 2
                and x['actual_text'] in record['original_text'] for x in foreign)): fail()
    if total > MAX_RECOVERY_CHARACTERS or len({r['pdf_fingerprint_sha256'] for r in records}) > 1 or len({r['report_year'] for r in records}) > 1:
        fail()
    return deepcopy(records)


def compact_native_text_recoveries(records, *, pdf_fingerprint=None, report_year=None):
    """Keep bounded full evidence; do not drop defaults or hashes at export."""
    return validate_native_text_recoveries(records, pdf_fingerprint=pdf_fingerprint, report_year=report_year)


def replay_native_text_recovery(page, *, pdf_fingerprint, report_year):
    if 'native_text_recovery' not in page:
        return str(page.get('text', '')), None
    records = validate_native_text_recoveries([page['native_text_recovery']],
        pdf_fingerprint=pdf_fingerprint, report_year=report_year)
    record = records[0]
    if (record['page_number'] != page.get('page_number') or record['original_text'] != page.get('text')
            or page.get('financial_geometry')):
        raise ValueError('原生恢复页面、默认原文或负号处理边界冲突，不能继续标准化。')
    return record['native_text'], record
