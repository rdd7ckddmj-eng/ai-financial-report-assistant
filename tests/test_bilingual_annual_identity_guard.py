"""Real bilingual Chinese annual originals are not English-only editions."""
from pathlib import Path
import json
import pytest
from src.annual_report_period_identity import has_disallowed_report_title
DATA=json.loads((Path(__file__).parent/'fixtures/coverage15_bilingual_annual_titles.json').read_text())
@pytest.mark.parametrize('sample',DATA,ids=lambda x:x['code']+str(x['year']))
def test_real_full_chinese_annual_with_parallel_english_title_is_allowed(sample):
    pages=[(p['page_number'],p['text']) for p in sample['pages']]
    assert not has_disallowed_report_title(pages)

@pytest.mark.parametrize('title',['Annual Report English Version','2025 Annual Report English Version','2025年度报告英文版','2025年度报告摘要','2025 Interim Report','2025半年度报告'])
def test_explicit_other_version_still_rejected(title):
    pages=[(p['page_number'],p['text']) for p in DATA[0]['pages']]
    pages[2]=(3,title+'\n'+pages[2][1])
    assert has_disallowed_report_title(pages)
