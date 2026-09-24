"""Bounded native-text identity for an annual report with an unreadable cover.

This only establishes company/period identity. It neither recovers missing
amounts nor declares that the three statements have reconciled.
"""
from hashlib import sha256
import re
from src.china_stock import infer_exchange

_SCHEMA = 'annual-report-period-identity.v1'
_KIND = 'native_period_definition_and_financial_statements'
_FRONT_PAGES = 10
_COVER_SEARCH_PAGES = 200
_FINANCIAL_WINDOW = 20
_GUARANTEE = '保证年度报告内容的真实性、准确性、完整性'
_STOCK_HEADER = ['股票种类', '股票上市交易所', '股票简称', '股票代码', '变更前股票简称']
_ROLES = ('annual_report_guarantee', 'glossary_heading', 'report_period_definition',
          'company_profile', 'a_share_listing', 'financial_statement_cover',
          'consolidated_balance_sheet', 'consolidated_income_statement',
          'consolidated_cash_flow_statement')
_AMOUNT = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
_NUMBER = re.compile(rf'(?:-?{_AMOUNT}|\({_AMOUNT}\))')


def _compact(text):
    return re.sub(r'\s+', '', text).replace('（', '(').replace('）', ')').replace(':', '：')


def _lines(text):
    lines=[]; start=0
    for raw in text.splitlines(keepends=True):
        value=raw.rstrip('\r\n')
        if value.strip():
            lines.append(dict(value=_compact(value), start=start, end=start+len(value)))
        start+=len(raw)
    return lines


def _source(role, number, text, start, end):
    return dict(role=role, page_number=number, char_start=start, char_end=end,
                excerpt=text[start:end], page_sha256=sha256(text.encode()).hexdigest())


def _span(role, number, text, lines, first, last):
    return _source(role, number, text, lines[first]['start'], lines[last]['end'])


def _period_pattern(year):
    chinese=[''.join(digits[int(c)] for c in str(year)) for digits in ('〇一二三四五六七八九', '零一二三四五六七八九')]
    y='(?:'+'|'.join([str(year), *chinese])+')'
    end=rf'{y}年(?:12|十二)月(?:31|三十一)日'
    return rf'报告期指{y}年(?:1|一)月(?:1|一)日至{end}报告期末指{end}'


def _statement(role, number, text, kind, legal_name, year):
    lines=_lines(text); values=[x['value'] for x in lines]
    if len(values)<10 or values[:1]!=[legal_name] or not re.fullmatch(r'第\d+页', values[1]):
        return None
    if values[2]!=kind:
        return None
    dated=kind=='合并资产负债表'
    if values[3]!=(f'{year}年12月31日' if dated else f'{year}年度'):
        return None
    unit=re.fullmatch(r'\(金额单位：人民币(元|千元|万元|百万元)\)', values[4])
    if not unit:
        return None
    prefix=6 if dated else 5
    if dated and values[5]!='资产':
        return None
    if not re.fullmatch(r'附注[一二三四五六七八九十]+', values[prefix]):
        return None
    periods=([f'{year}年','12月31日',f'{year-1}年','12月31日'] if dated
             else [f'{year}年',f'{year-1}年'])
    if values[prefix+1:prefix+1+len(periods)]!=periods:
        return None
    body_start=prefix+1+len(periods)
    first={'合并资产负债表':'流动资产', '合并利润表':'一、营业收入',
           '合并现金流量表':'一、经营活动产生的现金流量'}[kind]
    if values[body_start]!=first:
        return None
    anchor={'合并资产负债表':'资产总计', '合并利润表':'一、营业收入',
            '合并现金流量表':'经营活动产生的现金流量净额'}[kind]
    matches=[i for i,v in enumerate(values) if v==anchor]
    if len(matches)!=1:
        return None
    index=matches[0]+1
    if not dated:
        if not re.fullmatch(r'[1-9]\d{0,2}', values[index]):
            return None
        index+=1
    if len(values)<=index+1 or not all(_NUMBER.fullmatch(v) for v in values[index:index+2]):
        return None
    # The identity anchor is two original period cells, never a borrowed third.
    if len(values)>index+2 and _NUMBER.fullmatch(values[index+2]):
        return None
    return _span(role,number,text,lines,0,index+1),unit[1]


def has_disallowed_report_title(pages, *, company=None):
    """Reject explicit front-page report titles, not ordinary prose mentions."""
    year = r'(?:\d{4}|[〇零一二三四五六七八九]{4})年?'
    prefixes = [r'[\u4e00-\u9fffA-Za-z0-9()]{3,100}股份有限公司']
    if company and isinstance(company.get('name'), str) and company['name'] != '待核验公司':
        name = re.escape(_compact(company['name']))
        code = re.escape(str(company.get('code', '')))
        prefixes.append(rf'{name}(?:{code})?')
    issuer = '(?:' + '|'.join(prefixes) + ')?'
    kind = r'(?:(?:年度报告|年报)(?:\(?摘要\)?|\(?英文(?:版)?\)?)|(?:半年度|季度|中期)报告|(?:第?[一二三四1234]季度)报告|半年报|季报)'
    suffix = r'(?:\((?:修订版|修订稿|修订|更新版|更正后)\))?'
    pattern = re.compile(rf'{issuer}(?:{year})?{kind}(?:全文)?{suffix}')
    for _, text in list(pages)[:_FRONT_PAGES]:
        for line in _lines(text):
            value = line['value']
            if (pattern.fullmatch(value)
                    # Chinese originals may print a parallel "Annual Report"
                    # heading. Only an explicitly English-version heading is
                    # disallowed; the ordinary path still requires Chinese
                    # full-year identity and the fallback has its own proofs.
                    or re.fullmatch(r'(?:\d{4})?(?:annualreportenglishversion|(?:interimreport|quarterlyreport)(?:englishversion)?)', value, re.I)):
                return True
    return False


def recover_annual_report_period_identity(company, pages, report_year, *, pdf_fingerprint):
    """Return exact native source evidence, or None; no company/code allowlist."""
    try:
        return _recover(company, list(pages), report_year, pdf_fingerprint)
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def _recover(company, pages, year, pdf_fingerprint):
    if not isinstance(pdf_fingerprint, str) or not re.fullmatch(r'[0-9a-f]{64}', pdf_fingerprint):
        return None
    if type(year) is not int or not 1990<=year<2200 or not 10<=len(pages)<=1000:
        return None
    if any(type(n) is not int or not isinstance(t,str) for n,t in pages):
        return None
    if [n for n,_ in pages]!=list(range(1,len(pages)+1)):
        return None
    code=company.get('code'); name=company.get('name')
    exchange={'SH':'上海证券交易所','SZ':'深圳证券交易所','BJ':'北京证券交易所'}.get(company.get('exchange'))
    if not isinstance(code,str) or not re.fullmatch(r'\d{6}',code) or not exchange or not isinstance(name,str) or name=='待核验公司':
        return None
    if infer_exchange(code)!=company.get('exchange'):
        return None
    front=pages[:_FRONT_PAGES]; joined=_compact('\n'.join(t for _,t in front))
    if (has_disallowed_report_title(front, company=company)
            or re.search(r'(?:\d{4}|[〇零一二三四五六七八九]{4})年?(?:年度报告|年报)',joined)
            or re.search(r'annual\s*report|english\s*version','\n'.join(t for _,t in pages[:2]),re.I)):
        return None
    front_lines=[(n,t,_lines(t)) for n,t in front]
    guarantees=[_span(_ROLES[0],n,t,lines,i,i) for n,t,lines in front_lines
                for i,line in enumerate(lines) if _GUARANTEE in line['value']]
    periods=[(n,t,lines,i) for n,t,lines in front_lines for i,line in enumerate(lines)
             if re.match(r'^报告期(?=指|：|$)',line['value'])]
    period_ends=[line for _,_,lines in front_lines for line in lines
                 if re.match(r'^报告期末(?=指|：|$)',line['value'])]
    profiles=[(n,t,lines,i) for n,t,lines in front_lines for i,line in enumerate(lines)
              if line['value'].startswith('公司的中文名称')]
    stocks=[(n,t,lines,i) for n,t,lines in front_lines for i,line in enumerate(lines) if line['value']=='股票种类']
    if not all(len(x)==1 for x in (guarantees,periods,period_ends,profiles,stocks)):
        return None
    n,t,lines,i=periods[0]
    if not re.fullmatch(_period_pattern(year),''.join(x['value'] for x in lines[i:i+6])):
        return None
    definition=_span(_ROLES[2],n,t,lines,i,i+5)
    glossary=[_span(_ROLES[1],p,text,ls,j,j) for p,text,ls in front_lines if n-1<=p<=n
              for j,line in enumerate(ls) if line['value']=='释义' and (p<n or line['end']<=definition['char_start'])]
    if not glossary:
        return None
    p,t,lines,i=profiles[0]; values=[x['value'] for x in lines]
    if values[i]!='公司的中文名称' or values[i+2]!='公司的中文简称':
        return None
    legal_name,short_name=values[i+1],values[i+3]
    if not re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9()]{3,100}股份有限公司',legal_name) or name not in (legal_name,short_name):
        return None
    profile=_span(_ROLES[3],p,t,lines,i,i+3)
    sn,st,sl,si=stocks[0]; sv=[x['value'] for x in sl]
    if sn!=p or sv[si:si+5]!=_STOCK_HEADER or sv[si+5:si+9]!=['A股',exchange,short_name,code]:
        return None
    if sv[si+9] not in ('/','-','—','–',short_name):
        return None
    listing=_span(_ROLES[4],sn,st,sl,si,si+9)
    covers=[(n,t) for n,t in pages[10:_COVER_SEARCH_PAGES]
            if len(_compact(t))<=240 and '年度财务报表' in _compact(t)]
    if len(covers)!=1:
        return None
    cover_page,cover_text=covers[0]
    cover_expected=f'{legal_name}自{year}年1月1日至{year}年12月31日止年度财务报表'
    if _compact(cover_text)!=cover_expected or len(pages)<cover_page+_FINANCIAL_WINDOW:
        return None
    cl=_lines(cover_text); cover=_span(_ROLES[5],cover_page,cover_text,cl,0,len(cl)-1)
    scope=pages[cover_page:cover_page+_FINANCIAL_WINDOW]
    statement_sources=[]; units=[]; continuation_units=[]
    for role,kind in zip(_ROLES[6:],('合并资产负债表','合并利润表','合并现金流量表')):
        title_pattern=rf'(?:\d{{4}}年(?:度)?)?(?:\d+[、.．])?{kind}(?:\(续\))?'
        hits=[]
        for n,t in scope:
            ls=_lines(t);vs=[x['value'] for x in ls]
            if '目录' in vs[:5] and '页次' in vs[:6]:
                continue
            titles=[v for v in vs if re.fullmatch(title_pattern,v)]
            if not titles:
                continue
            if len(titles)!=1:
                return None
            if titles[0].endswith('(续)'):
                # A visible continuation must keep this issuer and current
                # period too. Blank image pages are not invented as evidence.
                date=f'{year}年12月31日' if kind=='合并资产负债表' else f'{year}年度'
                if (len(vs)<5 or vs[0]!=legal_name or not re.fullmatch(r'第\d+页',vs[1])
                        or vs[2]!=kind+'(续)' or vs[3]!=date):
                    return None
                unit=re.fullmatch(r'\(金额单位：人民币(元|千元|万元|百万元)\)',vs[4])
                prefix=6 if kind=='合并资产负债表' else 5
                expected=([f'{year}年','12月31日',f'{year-1}年','12月31日']
                          if kind=='合并资产负债表' else [f'{year}年',f'{year-1}年'])
                if (not unit or len(vs)<=prefix+len(expected)+1
                        or not re.fullmatch(r'附注[一二三四五六七八九十]+',vs[prefix])
                        or vs[prefix+1:prefix+1+len(expected)]!=expected
                        or re.search(r'\d{4}年',vs[prefix+1+len(expected)])):
                    return None
                continuation_units.append(unit[1])
                continue
            hits.append((n,t))
        if len(hits)!=1:
            return None
        record=_statement(role,*hits[0],kind,legal_name,year)
        if record is None:
            return None
        evidence,unit=record;statement_sources.append(evidence);units.append(unit)
    statement_pages=[x['page_number'] for x in statement_sources]
    if statement_pages!=sorted(set(statement_pages)) or len(set(units+continuation_units))!=1:
        return None
    sources=[guarantees[0],glossary[0],definition,profile,listing,cover,*statement_sources]
    # Audit text is optional: an image-only audit paragraph never becomes OCR
    # evidence or defeats otherwise complete period/company/statement evidence.
    for n,text in scope:
        compact=_compact(text)
        audit=re.search(r'我们审计了(?:后附的)?([\u4e00-\u9fff]+股份有限公司).{0,80}?财务报表，包括(\d{4})年12月31日.{0,100}?(\d{4})年度',compact)
        if n<statement_pages[0] and audit and (audit[1]!=legal_name or audit.groups()[1:]!=(str(year),str(year))):
            return None
        if (n<statement_pages[0] and '审计报告' in compact and legal_name in compact
                and f'{year}年12月31日' in compact and f'{year}年度' in compact
                and re.search(r'按照.{0,80}企业会计准则.{0,80}编制',compact)):
            start=text.find('审计报告');boundary=text.find('二、',start)
            end=text.find('\n',boundary) if boundary>=0 else -1
            if end<0:
                end=len(text)
            if start>=0 and boundary>start:
                sources.append(_source('native_cas_audit_opinion',n,text,start,end))
                break
    return dict(schema=_SCHEMA,kind=_KIND,pdf_fingerprint_sha256=pdf_fingerprint,report_year=year,company_code=code,
                legal_name=legal_name,short_name=short_name,exchange_name=exchange,
                financial_cover_page=cover_page,financial_window_end=cover_page+_FINANCIAL_WINDOW,
                statement_unit=units[0],sources=sources,no_ocr=True,original_text_preserved=True,
                human_verification='not_performed')


def validate_annual_identity_evidence(evidence, *, company=None, report_year=None, pages=None, pdf_fingerprint=None):
    """Validate a nonempty identity record; optionally bind every slice to pages.

    Empty dictionaries mean no alternate identity and return False. Callers
    with an optional field should first test whether that field is nonempty.
    """
    try:
        if not isinstance(evidence,dict) or evidence.get('schema')!=_SCHEMA or evidence.get('kind')!=_KIND:
            return False
        stored_fingerprint = evidence.get('pdf_fingerprint_sha256')
        if not isinstance(stored_fingerprint, str) or not re.fullmatch(r'[0-9a-f]{64}', stored_fingerprint):
            return False
        if pdf_fingerprint is not None and pdf_fingerprint != stored_fingerprint:
            return False
        year=evidence['report_year']
        if report_year is not None and (type(report_year) is not int or year!=report_year):
            return False
        bound_company=company if company is not None else dict(code=evidence['company_code'],name=evidence['short_name'],
            exchange={v:k for k,v in {'SH':'上海证券交易所','SZ':'深圳证券交易所','BJ':'北京证券交易所'}.items()}[evidence['exchange_name']])
        if evidence.get('no_ocr') is not True or evidence.get('original_text_preserved') is not True:
            return False
        if pages is not None:
            pages=list(pages)
            if _recover(bound_company,pages,year,stored_fingerprint)!=evidence:
                return False
        sources=evidence['sources']
        if not isinstance(sources,list) or len(sources) not in (len(_ROLES),len(_ROLES)+1):
            return False
        if [s.get('role') for s in sources]!=list(_ROLES)+(['native_cas_audit_opinion'] if len(sources)>len(_ROLES) else []):
            return False
        full=dict(pages) if pages is not None else None
        proof={};hashes={}
        for s in sources:
            if set(s)!={'role','page_number','char_start','char_end','excerpt','page_sha256'}:
                return False
            n,a,b=s['page_number'],s['char_start'],s['char_end']; text=s['excerpt']
            if (any(type(x) is not int for x in (n,a,b)) or not 1<=n<=220 or not 0<=a<b<=100000
                    or not isinstance(text,str) or len(text)!=b-a or not re.fullmatch(r'[0-9a-f]{64}',s['page_sha256'])):
                return False
            if n in hashes and hashes[n]!=s['page_sha256']:
                return False
            hashes[n]=s['page_sha256']
            if full is not None and (n not in full or full[n][a:b]!=text or sha256(full[n].encode()).hexdigest()!=s['page_sha256']):
                return False
            # Replaying only the declared exact excerpts checks the evidence's
            # own semantics without treating a recorded checksum as proof of PDF bytes.
            page=proof.setdefault(n,{})
            for offset,char in enumerate(text,a):
                if offset in page and page[offset]!=char:
                    return False
                page[offset]=char
        count=evidence['financial_window_end']
        if type(count) is not int or not 11<=count<=220:
            return False
        reconstructed=[(n,''.join(proof[n].get(i,'\n') for i in range(max(proof[n])+1)) if n in proof else '') for n in range(1,count+1)]
        replay=_recover(bound_company,reconstructed,year,stored_fingerprint)
        if replay is None or set(replay)!=set(evidence):
            return False
        if any(replay[k]!=evidence[k] for k in evidence if k!='sources'):
            return False
        return all({k:v for k,v in a.items() if k!='page_sha256'}=={k:v for k,v in b.items() if k!='page_sha256'}
                   for a,b in zip(replay['sources'],sources)) and len(replay['sources'])==len(sources)
    except (KeyError, TypeError, ValueError, IndexError):
        return False
