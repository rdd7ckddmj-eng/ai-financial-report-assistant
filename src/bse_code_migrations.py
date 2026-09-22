"""Explicit official BSE code aliases for current searches, not history rewrites."""
import json
from functools import lru_cache
from pathlib import Path

SOURCE_URL = 'https://www.bse.cn/service/code_mapping.html'


@lru_cache(maxsize=1)
def code_migrations():
    path = Path(__file__).resolve().parents[1] / 'data/reference/bse_code_migrations.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    result = {r['old_code']:r['new_code'] for r in data['entries']}
    if len(result)!=len(data['entries']) or len(set(result.values()))!=len(result):
        raise ValueError('北交所代码映射重复，不能推定身份。')
    return result


def current_bse_code(code):
    return code_migrations().get(str(code), str(code))
