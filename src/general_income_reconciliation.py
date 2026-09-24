"""Evidence-based arithmetic checks for bounded Chinese consolidated income tables.

This does not certify a full income statement or replace financial-sector
adapters. Missing evidence is different from a demonstrated amount mismatch.
"""
from decimal import Decimal, InvalidOperation, localcontext
import re

from src.financial_statement_extractor import (
    _normalise_lines, _chinese_label_span, _ordinary_shareholder_attribution_allowed,
    ORDINARY_SHAREHOLDER_PROFIT_LABEL,
)
from src.statement_evidence_rules import extract_statement_unit
from src.income_row_layout_recovery import recover_cross_page_attributable_profit, recover_cross_page_profit_before_tax
from src.statement_page_layout_recovery import recover_printed_statement_page_numbers
from src.signed_expense_presentation import signed_expense_presentation

_AMOUNT = r'(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?'
_NUMBER = re.compile(rf'^(?:[-—–]|[-−－]?{_AMOUNT}|\({_AMOUNT}\)|（{_AMOUNT}）)$')
_CN = '一二三四五六七八九十百'
_NOTE = re.compile(rf'^(?:附注)?(?:[{_CN}]+(?:[、.．]\d{{1,3}}|\([{_CN}A-Za-z0-9]+\)|、\([{_CN}]+\))|\([{_CN}]+\)(?:\d{{1,3}})?)(?:[,，、])?$')
_STRUCTURED_NOTE = re.compile(rf'^(?:[{_CN}]+、[{_CN}]+、\d{{1,3}}|\([{_CN}]+\)\d{{1,3}}[,，]\([{_CN}]+\)\d{{1,3}})$')
_COMPACT_NOTE = re.compile(rf'^[{_CN}]+[1-9]\d{{0,2}}$')
_ANNOTATION = re.compile(r'^\((?:(?:净亏损|亏损总额|亏损|损失)以[“"‘]?[-—–][”"’]?号填列|净亏损|亏损总额|亏损)\)')
_ALIASES = {
    # Read the long attributable label first so its wrapped "净利润" tail is
    # never mistaken for a second consolidated-total row.
    'attributable_profit': ('归属于母公司股东的净利润','归属于母公司所有者的净利润',ORDINARY_SHAREHOLDER_PROFIT_LABEL),
    'other_equity_holder_profit': ('归属于母公司其他权益工具持有者的净利润',),
    'minority_profit': ('少数股东损益',),
    'profit_before_tax': ('利润总额',),
    'income_tax': ('减：所得税(费用)/贷项','减：所得税费用','所得税费用'),
    'consolidated_net_profit': ('净利润',),
}


def _text(value):
    return value.replace('（','(').replace('）',')').replace(':','：').replace('−','-').replace('－','-')


def _compact(value):
    return re.sub(r'\s+','',_text(value))


def _value(token):
    token=_text(token)
    if len(token)>64 or not _NUMBER.fullmatch(token):raise ValueError('金额格式不完整')
    if token in ('-','—','–'):return Decimal(0)
    value=Decimal(token.strip('()').replace(',','').replace('，',''))
    if token.startswith('('):value=-value
    if not value.is_finite() or abs(value)>Decimal('1e24'):raise ValueError('金额超出支持范围')
    return value


def _financial_line(line, *, compact_notes=False, allow_parent_na=False):
    """Return explicit note and numeric tokens; arbitrary text is a boundary."""
    parts=_text(line).split()
    if not parts:return [],False
    numbers=[];has_note=False
    for part in parts:
        if _NUMBER.fullmatch(part) or (allow_parent_na and part in ('/', '不适用')):numbers.append(part)
        elif (_NOTE.fullmatch(_compact(part)) or (compact_notes and (
                _COMPACT_NOTE.fullmatch(_compact(part)) or _STRUCTURED_NOTE.fullmatch(_compact(part))))) and not numbers:has_note=True
        else:return None
    return numbers,has_note


def _match_label(lines,index,label, *, compact_notes=False, allow_parent_na=False):
    end=_chinese_label_span(lines,index,label)
    if end is None:return None
    merged=_text(' '.join(lines[index:end+1])).strip()
    merged=re.sub(rf'^(?:\d+\s*[.．、]|[{_CN}]+\s*[、.．])\s*','',merged,count=1)
    pattern=''.join(re.escape(ch)+r'\s*' for ch in _text(label))
    match=re.match(pattern,merged)
    if not match:return None
    tail=merged[match.end():].strip()
    annotation=_ANNOTATION.match(_compact(tail))
    if annotation:
        # Annotation text has no amounts; preserve any same-line cells after it.
        closing=tail.find(')')
        tail=tail[closing+1:].strip()
    if tail and _financial_line(tail, compact_notes=compact_notes, allow_parent_na=allow_parent_na) is None:return None
    return end,tail


def _rows(lines,page_numbers,column_count):
    found={key:[] for key in _ALIASES};reserved=set()
    first_row = next((i for i in range(len(lines)) if any(_match_label(lines,i,label) is not None
        for label in ('营业总收入','营业收入','其中：营业收入'))), 0)
    has_note_header=any(re.fullmatch(r'(?:项目)?附注['+_CN+r']*(?:\d{4}年(?:度)?)*',_compact(line))
                        for line in lines[:first_row])
    for index in range(len(lines)):
        if index in reserved:continue
        for key,labels in _ALIASES.items():
            parent_na = key in ('minority_profit', 'attributable_profit') and column_count == 4
            match=None
            for label in labels:
                if label == ORDINARY_SHAREHOLDER_PROFIT_LABEL and not _ordinary_shareholder_attribution_allowed(lines, index):
                    continue
                label_match=_match_label(lines,index,label, compact_notes=has_note_header, allow_parent_na=parent_na)
                if label_match is not None:
                    match=(label,label_match)
                    break
            if match is None:continue
            label,(end,tail)=match
            reserved.update(range(index+1,end+1))
            parts=[];last=end;notes=[];error=None;annotation_consumed=False
            remaining=([(tail,end)] if tail else [])+[(lines[i],i) for i in range(end+1,min(end+9,len(lines)))]
            cursor=0
            while cursor<len(remaining):
                line,line_number=remaining[cursor]
                if not parts and not annotation_consumed and _ANNOTATION.fullmatch(_compact(line)):
                    annotation_consumed=True
                    last=line_number
                    cursor+=1
                    continue
                parsed=_financial_line(line, compact_notes=has_note_header, allow_parent_na=parent_na)
                if parsed is None:
                    # Numeric note references can wrap across lines (五(四十/七)).
                    if not parts:
                        joined='';note_end=None
                        for extra in range(cursor,min(cursor+3,len(remaining))):
                            joined+=_compact(remaining[extra][0])
                            if _NOTE.fullmatch(joined) or (has_note_header and (
                                    _COMPACT_NOTE.fullmatch(joined) or _STRUCTURED_NOTE.fullmatch(joined))):note_end=extra;break
                        if note_end is not None:
                            notes.append(joined)
                            last=remaining[note_end][1]
                            cursor=note_end+1
                            continue
                    token=_compact(line)
                    if (re.match(r'^[+\-—–(.,?？\d]',token) and re.search(r'\d',token)
                            and not re.search(r'[\u4e00-\u9fff]',token)) or re.fullmatch(r'(?:不适用|无数据|N/?A|NAN|NULL|NONE)',token,re.IGNORECASE):
                        error='金额行含损坏的数字或未提供数值标记'
                    if re.fullmatch(r'(?:人民币|￥|¥)?[+\-]?[\d,，.]+(?:百万元|万元|千元|元)', token):
                        error='金额行含带单位的额外数值格'
                    break
                numbers,is_note=parsed
                if is_note:
                    if parts:error='附注出现在金额列之后';break
                    notes.append(line)
                parts.extend(numbers)
                last=line_number
                cursor+=1
            if (key=='income_tax' and has_note_header and not notes and len(parts)==column_count+1
                    and re.fullmatch(r'\d{1,3}',parts[0])):
                notes.append(parts.pop(0))
            try:
                if error:raise ValueError(error)
                if len(parts)!=column_count:raise ValueError('金额列数不是明确的本期/比较期列数')
                if any(p in ('/', '不适用') for p in parts):
                    allowed_na = [['不适用', '不适用']] + ([['/', '/']] if key == 'minority_profit' else [])
                    if not parent_na or parts[2:] not in allowed_na or any(p in ('/', '不适用') for p in parts[:2]):
                        raise ValueError('不适用标记必须成对位于归属行的两个公司列')
                    values=tuple(_value(p) for p in parts[:2]) + (None, None)
                else:
                    values=tuple(_value(p) for p in parts)
            except (ValueError,InvalidOperation) as exc:
                values=None;error=str(exc)
            found[key].append(dict(label=label,values=values,error=error,
                pages=dict(start=page_numbers[index],end=page_numbers[min(last,len(page_numbers)-1)]),
                excerpt=' ｜ '.join(lines[index:min(last+1,len(lines))]),notes=notes,
                _line_span=(index,last)))
            if values is not None and (any(p in ('/', '不适用') for p in parts)
                    or (key == 'income_tax' and all(p.startswith('(') for p in parts))):
                found[key][-1]['raw_values'] = list(parts)
            break
    return found


def _other_equity_attribution_context(lines, found, columns):
    """Only explicit sibling attribution rows can introduce a third summand."""
    totals = [i for i in range(len(lines)) if _match_label(lines, i, '净利润') is not None]
    if not totals:
        return bool(found['other_equity_holder_profit']), False
    start = totals[0]
    end = next((i for i in range(start + 1, len(lines)) if re.match(
        rf'^(?:[{_CN}]+[、.．])?其他综合收益', _compact(lines[i]))), len(lines))
    section = ''.join(_compact(line) for line in lines[start:end])
    present = '其他权益工具' in section or '权益工具持有者' in section or bool(found['other_equity_holder_profit'])
    if not present:
        return False, False
    headings = [i for i in range(start, end) if re.fullmatch(
        rf'(?:\([{_CN}]+\))?按所有权归属分类[：:]?', _compact(lines[i]))]
    if columns != 2 or len(headings) != 1:
        return True, False
    # These labels distinguish ordinary shareholder profit from the independent
    # other-equity-holder row. A “其中” child or unknown scope is not additive.
    indices=[];enumerations=[];covered=set()
    for key in ('attributable_profit', 'other_equity_holder_profit', 'minority_profit'):
        matches=found[key]
        if len(matches) != 1 or matches[0]['values'] is None:
            return True, False
        label=matches[0]['label']
        if key == 'attributable_profit' and label == '归属于母公司所有者的净利润':
            return True, False
        positions=[i for i in range(headings[0] + 1, end) if _match_label(lines, i, label) is not None]
        if len(positions) != 1:
            return True, False
        index=positions[0]
        number=re.match(r'^(\d+)[.．、]', _compact(lines[index]))
        if number is None:
            return True, False
        indices.append(index);enumerations.append(int(number[1]))
        span=matches[0].get('_line_span')
        if span is None:
            return True, False
        first,last=span
        covered.update(range(first,last+1))
    # An isolated “其中” or unknown scope sentence between sibling rows can
    # change their hierarchy. Numbering alone must never override that text.
    complete_section=covered == set(range(headings[0]+1,end))
    return True, complete_section and indices == sorted(indices) and enumerations == [1, 2, 3]


_PERIOD_QUALIFIER = r'(?:\((?:重述|经重述|已重述|调整后)\))?'
_RELATIVE_PERIOD = r'(?:本年|上年|本期|上期)发生额|(?:本期|上期)金额'


def _relative_period_cells(item):
    if re.fullmatch(r'(?:(?:' + _RELATIVE_PERIOD + r')' + _PERIOD_QUALIFIER + r')+', item):
        return re.findall(_RELATIVE_PERIOD, item)
    return None


def _has_open_period_qualifier(item):
    return (re.match(r'^(?:\d{4}年|' + _RELATIVE_PERIOD + r')', item)
            and item.count('(') > item.count(')'))


def _check_continuation_headers(lines, first_row, periods, relative, columns, resolved_years=None):
    """An explicit repeated column header must agree even on a middle page."""
    qualifier=_PERIOD_QUALIFIER
    for index in range(first_row + 1, len(lines)):
        item=_compact(lines[index])
        if not re.fullmatch(r'项目(?:附注)?(?:(?:\d{4}年|' + _RELATIVE_PERIOD + r').*)?', item):
            continue
        if relative and resolved_years:
            for preceding in lines[max(first_row + 1, index - 8):index]:
                previous = _compact(preceding)
                if re.fullmatch(r'\d{4}年(?:度|[\d月日—–-]+)', previous):
                    subtitle = re.fullmatch(r'(\d{4})年(?:度|1[-—–]12月)', previous)
                    if subtitle is None or int(subtitle[1]) != resolved_years[0]:
                        raise ValueError('续页相对期间的年度标题与首表不一致')
        repeated=[];repeated_relative=[];roles=[]
        cursor=index
        while cursor < min(index + 16, len(lines)):
            item=_compact(lines[cursor])
            if cursor == index:
                item=re.sub(r'^项目(?:附注)?', '', item)
            if not item or re.fullmatch(r'附注['+_CN+r']*', item):
                cursor+=1;continue
            if item in ('合并','公司','母公司'):
                roles.append(item);cursor+=1;continue
            if _has_open_period_qualifier(item):
                while cursor+1<len(lines) and item.count('(')>item.count(')'):
                    cursor+=1;item+=_compact(lines[cursor])
            if re.fullmatch(r'(?:\d{4}年(?:度)?'+qualifier+r')+',item):
                repeated.extend(int(y) for y in re.findall(r'(\d{4})年',item))
            elif re.search(r'\d{4}年',item):
                raise ValueError('续页年份列含未识别的期间或注释')
            elif _relative_period_cells(item) is not None:
                repeated_relative.extend(_relative_period_cells(item))
            elif re.search(_RELATIVE_PERIOD, item):
                raise ValueError('续页相对期间列含未识别的期间或注释')
            else:
                break
            cursor+=1
        if periods:
            if repeated != periods or repeated_relative:
                raise ValueError('续页本期/比较期年份列与首表不一致')
        elif repeated or repeated_relative != relative:
            raise ValueError('续页本期/比较期列与首表不一致')
        if roles and (columns != 4 or roles not in (
                ['合并','合并','公司','公司'], ['合并','合并','母公司','母公司'])):
            raise ValueError('续页合并及母公司列顺序不明确')


def _bounded_lines(pages,figures):
    start=figures.get('page_number');end=figures.get('end_page_number',start)
    if type(start) is not int or type(end) is not int or not 0<=end-start<=2:
        raise ValueError('利润表页码范围缺失或超出三页窗口')
    selected=[(n,t) for n,t in pages if start<=n<=end]
    if [n for n,_ in selected]!=list(range(start,end+1)):raise ValueError('利润表页面缺失或重复')
    recovered = recover_printed_statement_page_numbers(selected, '利润表')
    layout_recoveries = []
    if recovered:
        selected, recovery = recovered
        layout_recoveries.append(recovery)
    stream=[]
    for n,text in selected:
        page_lines=_normalise_lines(text)
        for position,line in enumerate(page_lines):
            # Only an exact physical-page number at a true page edge is a page
            # marker. Never discard arbitrary integer tokens inside a table.
            if position in (0,len(page_lines)-1) and line==str(n):continue
            stream.append((n,line))
    if any('Group income statement'==line for _,line in stream):return [],[],0,None,[]
    enumeration=rf'(?:\d+[、.．]|\([{_CN}]+\)|[{_CN}]+[、.．])?'
    title=re.compile(r'^(?:\d{4}年度)?'+enumeration+r'合并(?P<combined>及公司)?利润表(?:\(续\))?$')
    starts=[i for i,(_,line) in enumerate(stream) if title.fullmatch(_compact(line))]
    if not starts:raise ValueError('未找到明确的中文合并利润表标题')
    first=starts[0];column_count=4 if title.fullmatch(_compact(stream[first][1])).group('combined') else 2
    scoped=[]
    for number,line in stream[first:]:
        c=_compact(line)
        if re.fullmatch(r'(?:\d{4}年度)?'+enumeration+r'(?:母公司|公司)(?:利润表|资产负债表|现金流量表)(?:\(续\))?',c):break
        if re.fullmatch(r'(?:\d{4}年度)?'+enumeration+r'合并(?:及公司)?(?:资产负债表|现金流量表)(?:\(续\))?',c):break
        scoped.append((number,line))
    lines=[l for _,l in scoped];numbers=[n for n,_ in scoped]
    first_row=next((i for i in range(len(lines)) if any(
        _match_label(lines,i,label) is not None
        for label in ('营业总收入','营业收入','其中：营业收入'))),None)
    if first_row is None:raise ValueError('无法确定利润表列头和收入行的边界')
    header=[_compact(line) for line in lines[:first_row]]
    anchor=max((i for i,line in enumerate(header) if line.startswith('项目')
        or re.fullmatch(r'附注['+_CN+r']*',line)),default=0)
    # Preserve same-line years after “项目 [附注]”; subtitle years before this
    # column heading are not period columns.
    subtitle_years = [int(m[1]) for item in header[:anchor]
                      if (m := re.fullmatch(r'(\d{4})年(?:度|1[-—–]12月)', item))]
    if any(re.fullmatch(r'\d{4}年[\d月日度—–-]+', item)
           and not re.fullmatch(r'\d{4}年(?:度|1[-—–]12月)', item) for item in header[:anchor]):
        raise ValueError('利润表年度标题旁存在非完整年度期间')
    header=header[anchor:]
    header[0]=re.sub(r'^(?:项目(?:附注)?|附注['+_CN+r']*)','',header[0])
    qualified_relative = any(re.search(r'(?:' + _RELATIVE_PERIOD + r')\(', item) for item in header)
    periods=[];relative=[];cursor=0
    while cursor<len(header):
        item=header[cursor]
        # CRRC 2025 wraps its exact comparative qualifier as “2024年度(重 / 述)”.
        # Join only an unfinished year qualifier, never arbitrary header prose.
        if _has_open_period_qualifier(item):
            while cursor+1<len(header) and item.count('(')>item.count(')'):
                cursor+=1
                item+=header[cursor]
        qualifier=_PERIOD_QUALIFIER
        if re.fullmatch(r'(?:\d{4}年(?:度)?'+qualifier+r')+',item):
            periods.extend(int(y) for y in re.findall(r'(\d{4})年',item))
        elif re.search(r'\d{4}年',item):
            raise ValueError('年份列含未识别的期间或注释')
        elif _relative_period_cells(item) is not None:
            relative.extend(_relative_period_cells(item))
        elif re.search(_RELATIVE_PERIOD, item):
            raise ValueError('相对期间列含未识别的期间或注释')
        cursor+=1
    if periods:
        expected=[periods[0],periods[0]-1]*(column_count//2)
        if periods!=expected or relative:raise ValueError('本期/比较期年份列顺序或列数不明确')
    elif relative == ['本期金额','上期金额'] and column_count == 2:
        if len(subtitle_years) != 1:
            raise ValueError('本期金额表头缺少唯一完整年度标题')
        periods = [subtitle_years[0], subtitle_years[0] - 1]
    elif relative not in (['本年发生额','上年发生额']*(column_count//2),['本期发生额','上期发生额']*(column_count//2)):
        raise ValueError('缺少明确的本期/比较期列头')
    elif subtitle_years or qualified_relative:
        if len(subtitle_years) != 1:
            raise ValueError('相对期间表头存在重复或冲突的年度标题')
        periods = [subtitle_years[0], subtitle_years[0] - 1]
    if column_count==4:
        roles=[_compact(x) for x in lines[:first_row] if _compact(x) in ('合并','公司','母公司')]
        if roles not in (['合并','合并','公司','公司'], ['合并','合并','母公司','母公司']):
            raise ValueError('合并及公司四列表头顺序不明确')
    _check_continuation_headers(lines, first_row, [] if relative else periods, relative, column_count, periods)
    return lines,numbers,column_count,periods[:2] or None,layout_recoveries


def check_general_income_reconciliation(pages, income, *, report_year=None):
    """Check tax-to-net and profit attribution in the already selected table.

    The caller must use this only for its general Chinese template, after unit
    inheritance. All monetary output uses original units and Decimal strings.
    """
    result=dict(status='missing_evidence',passed=False,checks=[],unit=str((income or {}).get('unit','')),
        pages=None,evidence={},tolerance=None,header_years=None,note='缺少完整利润表证据，未判定金额是否一致。')
    if not income:return result
    pages = list(pages)
    try:
        lines,numbers,columns,header_years,layout_recoveries=_bounded_lines(pages,income)
        if layout_recoveries:
            result['layout_recoveries'] = layout_recoveries
        if columns==0:
            result.update(status='not_applicable',note='英文报表沿用原有专用流程，本检查不适用。');return result
        result['pages']=dict(start=numbers[0],end=numbers[-1])
        result['header_years']=header_years
        if report_year is not None:
            if type(report_year) is not int or not 1990<=report_year<=2200:raise ValueError('报告年度无效')
            if header_years is not None and header_years!=[report_year,report_year-1]:raise ValueError('利润表年度列与所选年报年度不一致')
        unit=_compact(result['unit']).removeprefix('人民币')
        local=extract_statement_unit(lines)
        if unit not in {'元','千元','万元','百万元'}:raise ValueError('缺少可核对的人民币金额单位')
        if local and _compact(local).removeprefix('人民币')!=unit:raise ValueError('利润表单位与提取金额单位不一致')
        if not local and any(re.search(r'单位(?:(?:均)?为[：:]?|[：:])(?:人民币)?(?:百万元|万元|千元|元|美元|港元)|^人民币(?:百万元|万元|千元|元)$|币种[：:]?',_compact(line)) for line in lines):
            raise ValueError('利润表含冲突或不受支持的单位声明')
        found=_rows(lines,numbers,columns)
        tax = found['profit_before_tax']
        if not tax or (len(tax) == 1 and tax[0]['values'] is None):
            selected_pages = [(n, text) for n, text in pages if numbers[0] <= n <= numbers[-1]]
            recovery = recover_cross_page_profit_before_tax(selected_pages, report_year=report_year)
            if (recovery and recovery['values'] is not None and columns == 2
                    and recovery['header_years'] == header_years and recovery['unit'] == unit):
                found['profit_before_tax'] = [recovery]
        attributable = found['attributable_profit']
        if not attributable or (len(attributable) == 1 and attributable[0]['values'] is None):
            selected_pages = [(n, text) for n, text in pages if numbers[0] <= n <= numbers[-1]]
            recovery = recover_cross_page_attributable_profit(selected_pages, report_year=report_year)
            if (recovery and recovery['values'] is not None and columns == 2
                    and recovery['header_years'] == header_years and recovery['unit'] == unit):
                found['attributable_profit'] = [recovery]
        other_present, other_independent = _other_equity_attribution_context(lines, found, columns)
        if not other_present:
            found.pop('other_equity_holder_profit')
        elif not other_independent:
            # Presence with an unknown scope is required missing evidence even
            # when the remaining two terms happen to add up without it.
            found['other_equity_holder_profit'] = []
        rows={};missing=[]
        for key,matches in found.items():
            if len(matches)!=1 or matches[0]['values'] is None:
                missing.append(key)
                result['evidence'][key]=dict(status='missing_or_ambiguous',note='必需行缺失、重复或金额列不完整')
            else:
                row=matches[0];rows[key]=row
                result['evidence'][key]={**{k:v for k,v in row.items() if k != '_line_span'},
                    'values':[str(v) if v is not None else None for v in row['values']]}
                if key in ('attributable_profit', 'minority_profit') and row['values'][2:] == (None, None):
                    result['evidence'][key]['not_applicable_columns'] = ['company_current', 'company_previous']
        required_values=[value for row in rows.values() for value in row['values'] if value is not None]
        integer_scaled=(unit in {'千元','万元','百万元'} and len(rows)==len(found)
            and all(v==v.to_integral_value() for v in required_values)
            and not any(re.search(r'\d\.\d',line) for line in lines))
        tolerance=Decimal('1') if integer_scaled else Decimal('.01')
        result['tolerance']=str(tolerance)
        result['rounding_note']='仅缩放且全整数报表允许1个原文显示单位的舍入差；不代表完全相等。' if integer_scaled else '金额差额上限为0.01个原文单位。'
        def add_check(key,label,keys,calculate,offset=0,allowed=None):
            allowed=tolerance if allowed is None else allowed
            check=dict(key=key,label=label,passed=False,current=None,previous=None)
            for period,index in (('current',offset),('previous',offset+1)):
                if any(k not in rows for k in keys):
                    check[period]=dict(left=None,right=None,difference=None,passed=False);continue
                with localcontext() as ctx:
                    ctx.prec=50
                    left,right=calculate(index)
                    delta=left-right
                check[period]=dict(left=str(left),right=str(right),difference=str(delta),passed=abs(delta)<=allowed)
            check['passed']=check['current']['passed'] and check['previous']['passed']
            result['checks'].append(check)
        def value(key,index):return rows[key]['values'][index]
        signed_tax=rows.get('income_tax',{}).get('label')=='减：所得税(费用)/贷项'
        presentation = signed_expense_presentation(lines, numbers, columns, unit, rows.get('income_tax', {}))
        if presentation:
            if not layout_recoveries:
                raise ValueError('带符号费用版式缺少同一公司、同一年度的连续页码证据')
            result['signed_expense_presentation'] = presentation
            signed_tax = True
        result['tax_presentation']='按明确“所得税(费用)/贷项”标签将带符号贷项加至利润总额' if signed_tax else '按所得税费用原有正负号从利润总额扣减'
        if presentation:
            result['tax_presentation'] = presentation['note']
        for offset,suffix in ((0,''),)+(((2,'_company'),) if columns==4 else ()):
            scope='母公司：' if offset else '合并：'
            tax_label='利润总额加带符号所得税费用/贷项等于净利润' if signed_tax else '利润总额减所得税费用等于净利润'
            add_check('profit_after_tax'+suffix,scope+tax_label,
                ('profit_before_tax','income_tax','consolidated_net_profit'),
                lambda i:(value('profit_before_tax',i)+(1 if signed_tax else -1)*value('income_tax',i),value('consolidated_net_profit',i)),offset)
            parent_attribution_na = rows.get('attributable_profit',{}).get('values', ())[2:] == (None, None)
            parent_minority_na = rows.get('minority_profit',{}).get('values', ())[2:] == (None, None)
            if offset and parent_attribution_na:
                if not parent_minority_na:
                    raise ValueError('公司利润归属行的不适用范围不一致')
                if any(rows[key].get('raw_values', [])[2:] != ['不适用', '不适用']
                       for key in ('attributable_profit', 'minority_profit')):
                    raise ValueError('两行公司归属格必须保留一致的原文“不适用”标记')
                for key, boundary in (('attributable_profit', '少数股东损益'),
                                      ('minority_profit', '其他综合收益的税后净额')):
                    end = rows[key]['_line_span'][1]
                    if end + 1 >= len(lines) or not re.fullmatch(
                            rf'(?:[{_CN}]+[、.．]|\d+[、.．])?' + re.escape(boundary), _compact(lines[end + 1])):
                        raise ValueError('公司不适用归属行后存在未知文字或额外金额')
                result.setdefault('not_applicable_checks', []).append(dict(
                    key='profit_attribution_company',
                    note='公司栏的归母与少数股东损益均明确为“不适用”；公司利润归属关系不执行计算，未补零、未计作通过。'))
            elif offset and parent_minority_na:
                add_check('profit_attribution'+suffix,scope+'股东净利润等于净利润（少数股东栏不适用，未作零值计算）',
                    ('attributable_profit','consolidated_net_profit'),
                    lambda i:(value('attributable_profit',i),value('consolidated_net_profit',i)),offset)
            else:
                attribution_keys=('attributable_profit','minority_profit') + (('other_equity_holder_profit',) if other_present else ())
                attribution_label=('归母股东利润加独立其他权益工具持有者利润加少数股东损益等于净利润'
                                   if other_present else '归母利润加少数股东损益等于净利润')
                add_check('profit_attribution'+suffix,scope+attribution_label,
                    attribution_keys+('consolidated_net_profit',),
                    lambda i:(sum(value(k,i) for k in attribution_keys),value('consolidated_net_profit',i)),offset)
        # Couple the reconciled row to the amount actually exposed to the user.
        candidate=[]
        for key in ('current_net_profit','previous_net_profit'):
            val=income.get(key)
            if isinstance(val,bool) or val is None:raise ValueError('提取的归母利润缺失或无效')
            number=Decimal(str(val))
            if not number.is_finite():raise ValueError('提取的归母利润非有限数')
            candidate.append(number)
        add_check('selected_attributable_profit','输出归母利润与原文归母行一致',('attributable_profit',),
            lambda i:(value('attributable_profit',i),candidate[i]),allowed=Decimal('.01'))
        mismatched=any(any(p['difference'] is not None and not p['passed'] for p in (c['current'],c['previous'])) for c in result['checks'])
        if mismatched:
            result.update(status='mismatch',note='利润表已取得的金额关系存在不一致，请核对原文；缺失行仍不补零。')
        elif missing:
            result.update(note='必需的税前利润、所得税、合并净利润、归母利润、少数股东行或已列其他权益工具持有者行存在缺失/歧义，不能宣称勾稽通过。')
        else:
            result.update(status='passed',passed=True,note='两期税前至税后利润关系、利润归属关系和输出归母行通过金额检查；这不是全利润表审计，收入与成本全部分项尚未逐项勾稽。')
        # An additional bounded layout can extend, but never silently replace,
        # the existing tax/attribution evidence. Unknown layouts keep that
        # original scope; complete contradictory evidence blocks a candidate.
        from src.general_operating_reconciliation import check_direct_operating_reconciliation
        operating = check_direct_operating_reconciliation(
            lines, numbers, columns, income, tolerance=tolerance)
        result['operating_reconciliation'] = operating
        if operating['status'] in ('passed', 'mismatch'):
            result['checks'].extend(operating['checks'])
            result['evidence'].update(operating['evidence'])
            if operating['status'] == 'mismatch':
                result.update(status='mismatch', passed=False,
                    note='利润表经营分项或输出营业收入存在不一致，请核对原文。' + operating['note'])
            elif result['status'] == 'passed':
                result['note'] = ('两期经营分项至税前利润、税前至税后利润、利润归属关系以及输出收入/归母行通过检查；'
                    '子项未重复加总，仍不代表完整财务审计。')
        else:
            result['note'] += ' ' + operating['note']
        if result.get('not_applicable_checks'):
            result['note'] += ' ' + ' '.join(item['note'] for item in result['not_applicable_checks'])
    except (ValueError,InvalidOperation,IndexError,TypeError) as exc:
        result.update(status='missing_evidence',passed=False,note='利润表证据不足：'+str(exc)+'。未判定金额是否一致。')
    return result
