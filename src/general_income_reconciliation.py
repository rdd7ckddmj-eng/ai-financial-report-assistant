"""Evidence-based arithmetic checks for bounded Chinese consolidated income tables.

This does not certify a full income statement or replace financial-sector
adapters. Missing evidence is different from a demonstrated amount mismatch.
"""
from decimal import Decimal, InvalidOperation, localcontext
import re

from src.financial_statement_extractor import _normalise_lines, _chinese_label_span
from src.statement_evidence_rules import extract_statement_unit

_AMOUNT = r'(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?'
_NUMBER = re.compile(rf'^(?:[-—–]|[-−－]?{_AMOUNT}|\({_AMOUNT}\)|（{_AMOUNT}）)$')
_CN = '一二三四五六七八九十百'
_NOTE = re.compile(rf'^(?:附注)?(?:[{_CN}]+(?:[、.．]\d{{1,3}}|\([{_CN}A-Za-z0-9]+\))|\([{_CN}]+\)\d{{1,3}})(?:[,，、])?$')
_COMPACT_NOTE = re.compile(rf'^[{_CN}]+[1-9]\d{{0,2}}$')
_ANNOTATION = re.compile(r'^\((?:(?:净亏损|亏损总额|亏损|损失)以[“"‘]?[-—–][”"’]?号填列|净亏损|亏损总额|亏损)\)')
_ALIASES = {
    # Read the long attributable label first so its wrapped "净利润" tail is
    # never mistaken for a second consolidated-total row.
    'attributable_profit': ('归属于母公司股东的净利润','归属于母公司所有者的净利润'),
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


def _financial_line(line, *, compact_notes=False):
    """Return explicit note and numeric tokens; arbitrary text is a boundary."""
    parts=_text(line).split()
    if not parts:return [],False
    numbers=[];has_note=False
    for part in parts:
        if _NUMBER.fullmatch(part):numbers.append(part)
        elif (_NOTE.fullmatch(_compact(part)) or (compact_notes and _COMPACT_NOTE.fullmatch(_compact(part)))) and not numbers:has_note=True
        else:return None
    return numbers,has_note


def _match_label(lines,index,label, *, compact_notes=False):
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
    if tail and _financial_line(tail, compact_notes=compact_notes) is None:return None
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
            match=None
            for label in labels:
                label_match=_match_label(lines,index,label, compact_notes=has_note_header)
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
                parsed=_financial_line(line, compact_notes=has_note_header)
                if parsed is None:
                    # Numeric note references can wrap across lines (五(四十/七)).
                    if not parts:
                        joined='';note_end=None
                        for extra in range(cursor,min(cursor+3,len(remaining))):
                            joined+=_compact(remaining[extra][0])
                            if _NOTE.fullmatch(joined) or (has_note_header and _COMPACT_NOTE.fullmatch(joined)):note_end=extra;break
                        if note_end is not None:
                            notes.append(joined)
                            last=remaining[note_end][1]
                            cursor=note_end+1
                            continue
                    token=_compact(line)
                    if (re.match(r'^[+\-—–(.,\d]',token) and re.search(r'\d',token)
                            and not re.search(r'[\u4e00-\u9fff]',token)) or re.fullmatch(r'(?:不适用|无数据|N/?A|NAN|NULL|NONE)',token,re.IGNORECASE):
                        error='金额行含损坏的数字或未提供数值标记'
                    break
                numbers,is_note=parsed
                if is_note:
                    if parts:error='附注出现在金额列之后';break
                    notes.append(line)
                parts.extend(numbers)
                last=line_number
                cursor+=1
            if (key=='income_tax' and has_note_header and len(parts)==column_count+1
                    and re.fullmatch(r'\d{1,3}',parts[0])):
                notes.append(parts.pop(0))
            try:
                if error:raise ValueError(error)
                if len(parts)!=column_count:raise ValueError('金额列数不是明确的本期/比较期列数')
                values=tuple(_value(p) for p in parts)
            except (ValueError,InvalidOperation) as exc:
                values=None;error=str(exc)
            found[key].append(dict(label=label,values=values,error=error,
                pages=dict(start=page_numbers[index],end=page_numbers[min(last,len(page_numbers)-1)]),
                excerpt=' ｜ '.join(lines[index:min(last+1,len(lines))]),notes=notes))
            break
    return found


def _bounded_lines(pages,figures):
    start=figures.get('page_number');end=figures.get('end_page_number',start)
    if type(start) is not int or type(end) is not int or not 0<=end-start<=2:
        raise ValueError('利润表页码范围缺失或超出三页窗口')
    selected=[(n,t) for n,t in pages if start<=n<=end]
    if [n for n,_ in selected]!=list(range(start,end+1)):raise ValueError('利润表页面缺失或重复')
    stream=[]
    for n,text in selected:
        page_lines=_normalise_lines(text)
        for position,line in enumerate(page_lines):
            # Only an exact physical-page number at a true page edge is a page
            # marker. Never discard arbitrary integer tokens inside a table.
            if position in (0,len(page_lines)-1) and line==str(n):continue
            stream.append((n,line))
    if any('Group income statement'==line for _,line in stream):return [],[],0,None
    enumeration=rf'(?:\d+[、.．]|\([{_CN}]+\)|[{_CN}]+[、.．])?'
    title=re.compile(r'^(?:\d{4}年度)?'+enumeration+r'合并(?P<combined>及公司)?利润表(?:\(续\))?$')
    starts=[i for i,(_,line) in enumerate(stream) if title.fullmatch(_compact(line))]
    if not starts:raise ValueError('未找到明确的中文合并利润表标题')
    first=starts[0];column_count=4 if title.fullmatch(_compact(stream[first][1])).group('combined') else 2
    scoped=[]
    for number,line in stream[first:]:
        c=_compact(line)
        if re.fullmatch(enumeration+r'(?:母公司|公司)(?:利润表|资产负债表|现金流量表)(?:\(续\))?',c):break
        if re.fullmatch(enumeration+r'合并(?:资产负债表|现金流量表)(?:\(续\))?',c):break
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
    header=header[anchor:]
    header[0]=re.sub(r'^(?:项目(?:附注)?|附注['+_CN+r']*)','',header[0])
    periods=[];relative=[];cursor=0
    while cursor<len(header):
        item=header[cursor]
        # CRRC 2025 wraps its exact comparative qualifier as “2024年度(重 / 述)”.
        # Join only an unfinished year qualifier, never arbitrary header prose.
        if re.match(r'^\d{4}年',item) and item.count('(')>item.count(')'):
            while cursor+1<len(header) and item.count('(')>item.count(')'):
                cursor+=1
                item+=header[cursor]
        qualifier=r'(?:\((?:重述|经重述|已重述|调整后)\))?'
        if re.fullmatch(r'(?:\d{4}年(?:度)?'+qualifier+r')+',item):
            periods.extend(int(y) for y in re.findall(r'(\d{4})年',item))
        elif re.search(r'\d{4}年',item):
            raise ValueError('年份列含未识别的期间或注释')
        elif re.fullmatch(r'(?:(?:本年|上年|本期|上期)发生额)+',item):
            relative.extend(re.findall(r'(?:本年|上年|本期|上期)发生额',item))
        cursor+=1
    if periods:
        expected=[periods[0],periods[0]-1]*(column_count//2)
        if periods!=expected or relative:raise ValueError('本期/比较期年份列顺序或列数不明确')
    elif relative not in (['本年发生额','上年发生额']*(column_count//2),['本期发生额','上期发生额']*(column_count//2)):
        raise ValueError('缺少明确的本期/比较期列头')
    if column_count==4:
        roles=[_compact(x) for x in lines if _compact(x) in ('合并','公司')]
        if roles!=['合并','合并','公司','公司']:
            raise ValueError('合并及公司四列表头顺序不明确')
    return lines,numbers,column_count,periods[:2] or None


def check_general_income_reconciliation(pages, income, *, report_year=None):
    """Check tax-to-net and profit attribution in the already selected table.

    The caller must use this only for its general Chinese template, after unit
    inheritance. All monetary output uses original units and Decimal strings.
    """
    result=dict(status='missing_evidence',passed=False,checks=[],unit=str((income or {}).get('unit','')),
        pages=None,evidence={},tolerance=None,header_years=None,note='缺少完整利润表证据，未判定金额是否一致。')
    if not income:return result
    try:
        lines,numbers,columns,header_years=_bounded_lines(list(pages),income)
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
        if not local and any(re.search(r'单位(?:为[：:]?|[：:])(?:人民币)?(?:百万元|万元|千元|元|美元|港元)|^人民币(?:百万元|万元|千元|元)$|币种[：:]?',_compact(line)) for line in lines):
            raise ValueError('利润表含冲突或不受支持的单位声明')
        found=_rows(lines,numbers,columns)
        rows={};missing=[]
        for key,matches in found.items():
            if len(matches)!=1 or matches[0]['values'] is None:
                missing.append(key)
                result['evidence'][key]=dict(status='missing_or_ambiguous',note='必需行缺失、重复或金额列不完整')
            else:
                row=matches[0];rows[key]=row
                result['evidence'][key]={**row,'values':[str(v) for v in row['values']]}
        required_values=[value for row in rows.values() for value in row['values']]
        integer_scaled=(unit in {'千元','万元','百万元'} and len(rows)==5
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
        result['tax_presentation']='按明确“所得税(费用)/贷项”标签将带符号贷项加至利润总额' if signed_tax else '按所得税费用原有正负号从利润总额扣减'
        for offset,suffix in ((0,''),)+(((2,'_company'),) if columns==4 else ()):
            scope='母公司：' if offset else '合并：'
            tax_label='利润总额加带符号所得税费用/贷项等于净利润' if signed_tax else '利润总额减所得税费用等于净利润'
            add_check('profit_after_tax'+suffix,scope+tax_label,
                ('profit_before_tax','income_tax','consolidated_net_profit'),
                lambda i:(value('profit_before_tax',i)+(1 if signed_tax else -1)*value('income_tax',i),value('consolidated_net_profit',i)),offset)
            add_check('profit_attribution'+suffix,scope+'归母利润加少数股东损益等于净利润',
                ('attributable_profit','minority_profit','consolidated_net_profit'),
                lambda i:(value('attributable_profit',i)+value('minority_profit',i),value('consolidated_net_profit',i)),offset)
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
            result.update(note='必需的税前利润、所得税、合并净利润、归母利润或少数股东行存在缺失/歧义，不能宣称勾稽通过。')
        else:
            result.update(status='passed',passed=True,note='两期税前至税后利润关系、利润归属关系和输出归母行通过金额检查；这不是全利润表审计，收入与成本全部分项尚未逐项勾稽。')
    except (ValueError,InvalidOperation,IndexError,TypeError) as exc:
        result.update(status='missing_evidence',passed=False,note='利润表证据不足：'+str(exc)+'。未判定金额是否一致。')
    return result
