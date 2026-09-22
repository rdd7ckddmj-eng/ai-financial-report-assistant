import pandas as pd
from src.bse_code_migrations import current_bse_code, code_migrations
from src.china_stock import build_company_identity, resolve_company


def test_all_official_migrations_are_one_to_one_and_current_search_only():
    mapping=code_migrations()
    assert len(mapping)==248 and len(set(mapping.values()))==248
    for old,new in mapping.items():
        assert new.startswith('920') and len(new)==6
        assert resolve_company(old)[0]['code']==new
        assert build_company_identity(old)['code']==old
        assert current_bse_code(new)==new


def test_collision_mapping_is_explicit_not_last_three_digits():
    assert current_bse_code('836961')=='920061'
    assert current_bse_code('831961')=='920961'
    assert current_bse_code('831167')=='920267'
    assert current_bse_code('600519')=='600519'
    assert current_bse_code('899999')=='899999'


def test_current_code_lookup_uses_current_directory_and_name_search_migrates():
    directory=pd.DataFrame([{'code':'920961','name':'测试公司'}])
    assert resolve_company('831961',directory)[0]['name']=='测试公司'
    old_directory=pd.DataFrame([{'code':'831961','name':'测试公司'}])
    assert resolve_company('测试公司',old_directory)[0]['canonical_code']=='920961.BJ'
