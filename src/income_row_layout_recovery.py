"""Read one observed attributable-profit row whose sign annotation spans pages.

No text is rearranged. The original two monetary cells precede the second half
of the annotation in the PDF text stream. This helper validates that exact
layout, returns original source segments, and leaves arithmetic to the caller.
"""
from decimal import Decimal, InvalidOperation
import re

CROSS_PAGE_ATTRIBUTABLE_LAYOUT = 'attributable_profit_annotation_page_break_v1'
_LABEL = '归属于母公司股东的净利润'
_PREFIX = '1.' + _LABEL + '（净亏'
_SUFFIX = '损以“-”号填列）'
_MINOR = ['2.少数股东损益（净亏损以“-”号', '填列）']
_AMOUNT = re.compile(r'^-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}$')
_REPORT_HEADER = re.compile(r'^(?P<issuer>[\u4e00-\u9fffA-Za-z（）()·]+股份有限公司)(?P<year>\d{4})年年度报告$')
_MARKER = re.compile(r'^(?P<page>\d+)/(?P<total>\d+)$')


def _c(text):
    return re.sub(r'\s+', '', text)


def _lines(text):
    return [m for m in re.finditer(r'[^\r\n]+', text) if m.group().strip()]


def _money(text):
    token=text.strip()
    if len(token)>32 or not _AMOUNT.fullmatch(token):
        raise ValueError('跨页归母行必须有恰好两个明确的两位小数金额，不推定空白或破折号')
    value=Decimal(token.replace(',',''))
    if not value.is_finite() or abs(value)>Decimal('1e24'):
        raise ValueError('跨页归母行金额超出支持范围')
    return value


def recover_cross_page_attributable_profit(pages, *, report_year=None):
    """Return a source-grounded row, a recognized failure, or None for nonmatch.

    ``pages`` contains ordered ``(physical_page_number, original_text)`` pairs.
    A success row matches general_income_reconciliation._rows' row contract:
    label, values (Decimal pair), error, pages, excerpt, notes. Extra metadata
    preserves the exact original slices, source line order and currency/years.
    The helper does not establish issuer identity or reconcile financial totals.
    """
    pages=list(pages)
    candidates=[]
    for page_number,text in pages:
        for index,line in enumerate(_lines(text)):
            compact=_c(line.group())
            # Only an unfinished annotation after the complete core label is
            # a candidate; ordinary complete labels stay on the normal path.
            if (_LABEL in compact and '（' in compact
                    and '）' not in compact and compact.startswith('1.')):
                candidates.append((page_number,text,index))
    if not candidates:
        return None
    failure=dict(label=_LABEL,values=None,error='',pages=None,excerpt='',notes=[],
                 layout_recovery=CROSS_PAGE_ATTRIBUTABLE_LAYOUT,source_segments=[])
    try:
        numbers=[n for n,_ in pages]
        if (any(type(n) is not int or n<1 for n in numbers)
                or numbers!=sorted(set(numbers))):
            raise ValueError('跨页利润行的物理页码无效、重复或无序')
        if len(candidates)!=1:
            raise ValueError('跨页归母利润候选不唯一，不能选择或合并重复行')
        number,text,index=candidates[0]
        following=[t for n,t in pages if n==number+1]
        if len(following)!=1:
            raise ValueError('跨页归母行缺少紧邻的下一物理页')
        next_text=following[0]
        lines,next_lines=_lines(text),_lines(next_text)
        if len(lines)<12 or len(next_lines)<9:
            raise ValueError('跨页归母行前后页面不完整')
        header=_REPORT_HEADER.fullmatch(_c(lines[0].group()))
        marker=_MARKER.fullmatch(_c(lines[1].group()))
        next_marker=_MARKER.fullmatch(_c(next_lines[1].group()))
        if (header is None or marker is None or next_marker is None
                or _c(next_lines[0].group())!=_c(lines[0].group())
                or int(marker['page'])!=number or int(next_marker['page'])!=number+1
                or marker['total']!=next_marker['total']
                or not number+1<=int(marker['total'])<=1000):
            raise ValueError('不能确认同一份年报页眉和相邻物理页码，禁止删除任意插入行')
        year=int(header['year'])
        if not 1990<=year<=2199 or (report_year is not None and (type(report_year) is not int or report_year!=year)):
            raise ValueError('跨页行报告年度不匹配')
        compact=[_c(m.group()) for m in lines]
        titles=[i for i,line in enumerate(compact) if line=='合并利润表']
        if len(titles)!=1:
            raise ValueError('跨页行之前缺少唯一明确的合并利润表')
        title=titles[0]
        expected=['合并利润表',f'{year}年1—12月','单位：元','币种：人民币',
                  '项目','附注五',f'{year}年度',f'{year-1}年度','一、营业总收入']
        if compact[title:title+len(expected)]!=expected:
            raise ValueError('跨页行合并范围、人民币元、附注或本期/比较期双列表头不匹配')
        # The parent balance sheet may finish before the group income title,
        # but another statement may never intervene before this profit row.
        if index<=title or any(re.fullmatch(r'(?:母公司|公司|合并)(?:利润表|资产负债表|现金流量表)(?:（续）)?',s)
                              for s in compact[title+1:index]):
            raise ValueError('跨页归母行已越过合并利润表边界')
        if (compact[index]!=_PREFIX or index!=len(lines)-3
                or index<1 or compact[index-1]!='（二）按所有权归属分类'):
            raise ValueError('跨页归母行必须处于页尾，且核心标签、注释前缀和分类边界完整')
        values=tuple(_money(lines[i].group()) for i in (index+1,index+2))
        next_compact=[_c(m.group()) for m in next_lines]
        if next_compact[2:5]!=[_SUFFIX,*_MINOR]:
            raise ValueError('下一页注释后缀或少数股东行不连续，不能跳过其他行补齐')
        # Explicitly validate both cells of the following row to stop an extra
        # attributable amount from masquerading as its annotation or boundary.
        for i in (5,6):
            _money(next_lines[i].group())
        if next_compact[7]!='六、其他综合收益的税后净额':
            raise ValueError('下一页少数股东行金额后出现额外金额、未知行或母公司边界')
        # The exact core row must not appear again in the bounded group scope.
        next_end=next((i for i,s in enumerate(next_compact) if s=='母公司利润表'),len(next_compact))
        occurrences=sum(_LABEL in s for s in compact[title:]+next_compact[2:next_end])
        if occurrences!=1:
            raise ValueError('合并范围内归母净利润标签重复')
        first_segment=text[lines[index].start():lines[-1].end()]
        second_segment=next_text[next_lines[0].start():next_lines[2].end()]
        segments=[dict(page_number=number,text=first_segment,
                       start_offset=lines[index].start(),end_offset=lines[-1].end()),
                  dict(page_number=number+1,text=second_segment,
                       start_offset=next_lines[0].start(),end_offset=next_lines[2].end())]
        return dict(label=_LABEL,values=values,error=None,pages=dict(start=number,end=number+1),
                    amount_pages=dict(start=number,end=number),notes=[],
                    excerpt=first_segment+'\n'+second_segment,source_segments=segments,
                    header_years=[year,year-1],unit='元',currency='人民币',
                    layout_recovery=CROSS_PAGE_ATTRIBUTABLE_LAYOUT,
                    note='金额保留在前页；下一页仅用于确认原文括号注释完整，未调换或补造原文。')
    except (ValueError,InvalidOperation,IndexError,TypeError) as error:
        failure['error']=str(error)
        return failure
