# 已登记官方重述解释线索

`src/official_restatement_evidence.py` 读取本地 `data/reference/official_restatement_evidence.json`。当前有八个指标记录（七项资产负债、一项营业收入），不联网查找公告，不表示全市场自动识别重述，也不增加人工财务确认数。

| 公司及原年报 | 指标 | 原金额（元） | 后续重述金额（元） | 后续官方证据 |
|---|---|---:|---:|---|
| 汇川技术 300124.SZ，2025 | 总资产 | 71,314,393,635.15 | 71,314,783,635.15 | 2026一季报第2、7页金额；第2、11页原因 |
| 中国神华 601088.SH，2025 | 总资产 | 627,761,000,000 | 903,830,000,000 | 2026半年报第6、76页金额；第7页原因 |
| 中国神华 601088.SH，2025 | 总负债 | 146,310,000,000 | 300,203,000,000 | 2026半年报第6、77页金额；第7页原因 |
| 中国石油 601857.SH，2025 | 总资产 | 2,828,017,000,000 | 2,863,458,000,000 | 2026半年报第6页调整前后、第51页比较栏；第6、86页原因 |
| 中国石油 601857.SH，2025 | 总负债 | 1,028,469,000,000 | 1,032,684,000,000 | 原年报第108页原值、2026半年报第52页后值；第86页被并方上年末负债差额 |
| 中信证券 600030.SH，2024 | 营业收入 | 63,789,215,688.23 | 58,119,003,450.22 | 2025年报第19页调整前后、第182页比较栏；第230页原因 |
| 海螺水泥 600585.SH，2025 | 总资产 | 256,000,730,169 | 256,494,726,008 | 原年报第88页、2026半年报第60页经重述比较列；第8页原因 |
| 海螺水泥 600585.SH，2025 | 总负债 | 52,284,946,547 | 52,490,389,624 | 原年报第89页、2026半年报第61页经重述比较列；第8页原因 |

页码均为PDF物理页。神华原单位为人民币百万元，汇川为人民币元。JSON保留原始单位、原数、调整前后数、元金额、差额、报告标题、公告日、全文页数、官方PDF地址和完整SHA-256；原文依据见[汇川说明](HUICHUAN_ASSET_RESTATEMENT.md)与[神华说明](SHENHUA_BALANCE_RESTATEMENT.md)。

## 匹配接口

```python
match_official_restatement_evidence(
    company_code, report_year, annual_fingerprint,
    metric_key, annual_yuan, public_yuan,
)  # dict | None
```

六个参数必须全部匹配：带交易所的规范代码（如`300124.SZ`）、整数年度、原年报完整小写SHA-256、指标键、原年报金额，以及等于官方后续重述金额的公共值。不会仅凭相同差额、公司简称、年份或相近金额匹配。原年报SHA不同，即使金额相同也不返回解释。

金额用Decimal比较，不四舍五入、不使用容差。可接收十进制字符串、Decimal和正常数值；现有JSON浮点数按其字符串十进制表达比较，不补偿浮点误差。拒绝布尔值、缺失、NaN、Infinity、带千分位/单位说明的字符串。返回值中的金额统一为十进制字符串。

命中字段包括：`evidence_id/status/company_code/company_name/report_year/period_end/metric_key`，`annual_yuan/restated_yuan/difference_yuan`，`annual_report/subsequent_report`，`explanation/limitations`。报告字段均含`title/published_date/source_url/sha256/page_count`；原年报另有`amount_value/amount_unit/amount_pages`，旧记录后续报告另有`before_value/after_value/amount_unit/amount_pages/explanation_pages`。海螺采用显式双源模式 `evidence_basis=annual_original_to_subsequent_restated`：原值只来自原年报，后续元级表只有 `after_value`，禁止添造 `before_value`；另逐项约束两份报告的公司、年末时点、行名、合并口径、会计准则及列角色。详见[海螺双源登记](CONCH_DUAL_SOURCE_RESTATEMENT.md)。

每条命中保留`status=registered_official_restatement_explanation`、`effect=explanation_only`、`human_verification=not_performed`。这是已登记解释线索，不是自动确认。调用方须继续保留`difference`、原金额、公共金额及原有人工决定，不得改成`amount_close`或用后续数覆盖原报。

## 登记与校验边界

登记是经过来源调查后随代码发布的只读参考数据。加载时验证公司与交易所、年度时点、日期先后、官方HTTPS PDF地址、完整指纹、页码范围、已知人民币单位、两种原单位数到元的精确换算、差额及重复记录。汇川的原年报与一季报同日公告，允许同日后续报告；不从日期顺序推测供应商更新时间。

`validate_official_restatement_registry(data)` 可供测试显式验证完整性，损坏时抛出ValueError；匹配函数遇到登记缺失或损坏则返回None，不返回半份登记的结果。每次读取只访问本地文件，返回独立副本，调用方不能通过修改返回值污染后续匹配。它不重新下载PDF或证明登记内容的数字签名；SHA用于绑定此前调查的特定原文版本。

官方后续数字与公共值一致，只证明对应披露口径存在。供应商何时、如何采用报告仍未知；神华调查时公共行UPDATE_DATE仍为2026-03-31，不能当作后续重述数实际入库日期。后续报告只作解释来源，不计入完整年度报告覆盖数。

## 已保存记录的展示校验

`validated_stored_restatement_evidence(comparison, row)` 只验证当前传入的对照记录与其中保存的说明，返回独立证据副本或`None`。它不读取当前登记表、不调用匹配函数、不联网，也不在查看旧案件时更新原记录。

它接受`public-financial-reconciliation.v1`及`public-financial-reconciliation-artifact.v1`两种记录，先复用单条登记的完整性验证，再要求规范公司代码、整数年度、原年报SHA、官方原文地址、公告日期、指标、差异状态及两侧金额一致。行差额必须精确等于“原年报候选－公共值”；证据自身的重述增减额是“重述值－原值”，两者方向相反。更改公共值后即使重新计算行差额，也不能沿用原说明。

缺少旧字段、未知版本、损坏来源、金额错配或人工确认标记变化均返回`None`，交由页面提示重新核对，不猜测缺失内容。这是存档内部一致性检查，不是数字签名认证；仍不构成人工复核。

测试文件为`tests/test_official_restatement_evidence.py`，覆盖三个已登记指标、六维错配、微小金额差异、单位换算、非法来源、缺失原文元数据、损坏登记、重复记录、返回值隔离，以及已保存记录的金额/身份/来源一致性和禁止重新读表/联网。UI、JSON和研究案件接入由调用模块另行验证。

中国石油新增两项由 `tests/test_petrochina_restatement_evidence.py` 验证真实原文、登记字段、两源差异保留及错误金额不匹配；详细原件见 [储气库合并重述](PETROCHINA_BALANCE_RESTATEMENT.md)。

中信证券收入重述由 `tests/test_citic_restatement_evidence.py` 验证真实原文前后列、三项收入调整、精确匹配和差异状态保留；详细原件见 [中信2024收入重述](CITIC_REVENUE_RESTATEMENT.md)。支持指标键限于 `total_assets`、`total_liabilities`、`revenue`，不自动推断其他指标。

海螺双源证据及历史展示由 `tests/test_conch_restatement_evidence.py` 和 `tests/test_conch_restatement_display.py` 检查：原年报与后续报告各自金额/单位/物理页、禁止伪造后续调整前数、错误列与时点拒绝、差异状态保留，以及保存后不联网不重新匹配。
