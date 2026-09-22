from copy import deepcopy
import pytest
from src.china_stock import DataSourceError
from src.public_financial_history import build_public_financial_history
from src.public_financial_coverage_audit import audit_public_financial_coverage
from test_public_financial_ui import fixture_history


def test_sample_tracks_success_partial_and_failure_without_aborting():
    callbacks=[]
    def fetch(company):
        code=company['code']
        if code=='600036': raise DataSourceError('接口不可用')
        history=fixture_history(code)
        if code=='300750':
            rows=deepcopy(history['source_rows']); rows[-1]['OPERATE_INCOME_PK']=None
            history=build_public_financial_history(company,rows,fetched_at=history['fetched_at'])
        return history
    result=audit_public_financial_coverage(['000651','600036','300750'],fetcher=fetch,on_result=callbacks.append)
    assert result['counts']==dict(available=1,partial=1,unavailable=1)
    assert len(callbacks)==3
    assert result['rows'][2]['core_field_gaps'][0]['fields']==['revenue']
    assert '不是官方核验' in result['limitation']


@pytest.mark.parametrize('codes',[[],['000651']*21,['000651','000651'],['wrong']])
def test_invalid_sample_never_fetches(codes):
    def forbidden(*args): raise AssertionError('unexpected fetch')
    with pytest.raises(ValueError): audit_public_financial_coverage(codes,fetcher=forbidden)


def test_wrong_company_is_recorded_as_failure():
    result=audit_public_financial_coverage(['600036'],fetcher=lambda _:fixture_history('000651'))
    assert result['counts']['unavailable']==1
    assert '其他公司' in result['rows'][0]['reason']


def test_short_history_does_not_invent_missing_years():
    def fetch(company):
        h=fixture_history(company['code'])
        return build_public_financial_history(company,h['source_rows'][-1:],fetched_at=h['fetched_at'])
    result=audit_public_financial_coverage(['000651'],fetcher=fetch)
    assert result['counts']['available']==1 and len(result['rows'][0]['years'])==1
