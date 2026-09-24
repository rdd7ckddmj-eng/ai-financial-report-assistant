# 海螺水泥 2025 年末资产负债的双源重述解释

此接入沿用[第12批原件调查](COVERAGE12_RESTATEMENT_SOURCE.md)，新增两条本地登记，不重新解析年报，不修改五项候选金额、公开源金额、`amount_difference` 或人工决定。登记共八条，其中海螺两条使用明确的双源金额来源模式。

| 指标 | 2025 原年报原值（人民币元） | 2026 半年报的 2025-12-31 经重述比较值（人民币元） | 后续减原年报（元） | 原年报 / 后续 PDF 物理页 |
|---|---:|---:|---:|---|
| 资产总计 | 256000730169 | 256494726008 | 493995839 | 88 / 60 |
| 负债合计 | 52284946547 | 52490389624 | 205443077 | 89 / 61 |

两份表均为中国会计准则合并资产负债表。半年报为未经审计报表；第60、61页的比较列明确标注 `2025年12月31日（经重述）`。第8页说明收购安徽海螺绿能售电有限公司和海螺设计院属于同一控制下企业合并，需重述过往财务报表。第8页资产摘要单位为千元，其调整前后数字不可补成精确到元的证据；第10页国际准则负债摘要也不可替代中国准则合并负债。

- 原年报：[2026-03-25 公告](https://static.cninfo.com.cn/finalpage/2026-03-25/1225028852.PDF)，268页，SHA-256 `a50f3e7f150954b2b45c44c50afdaa618c4184ebe4bb1e9b3a2b6475267c66d8`。
- 后续半年报：[2026-08-27 公告](https://static.cninfo.com.cn/finalpage/2026-08-27/1225511652.PDF)，238页，SHA-256 `7c9b1464eb36998cad9e76c525e0979af53920c182951aa86cc4fc398efdce06`。

本批重新检查上述两份本地原件的字节SHA及88、89、8、60、61页既有渲染。上述金额均来自真实报表单元格；同日会计政策变更公告不是这两项差额的证据来源。

## 最小兼容扩展

外层仍是 `official-restatement-evidence.v1`。旧记录不含 `evidence_basis`，仍强制验证后续报告的 `before_value/after_value`，不放宽既有规则。

新增 `evidence_basis=annual_original_to_subsequent_restated` 时：

- 原值仅来自 `annual_report.amount_value`；后续值仅来自 `subsequent_report.after_value`。后续 `before_value` 必须不存在，即使为 `null` 或正确金额也拒绝。
- 两份报告分别保留自己的单位、页码、SHA、公告时间和官方URL，并各自验证元值换算，不要求共享原始单位。
- 每份报告必须绑定相同 `company_code`、`amount_period_end`，以及匹配指标的 `amount_label`。
- `amount_column` 分别限定为 `annual_current` 与 `restated_comparative`；`statement_scope=consolidated`、`accounting_basis=china_accounting_standards`。目前该模式只支持年末资产、负债，不扩展到利润表的年度与半年度期间。
- 两份PDF的SHA与URL必须不同。未知模式、缺项、错列、错时点、母公司或国际准则口径均拒绝。

产品显示应明确“原年报原列值 → 后续报告重述比较值”，分别给出金额单位和页码，不把原年报原值称作后续报告披露的调整前值。UI由调用模块接入，匹配模块不改对照状态或人工决定。

## 回执与验证边界

`tests/fixtures/conch_restatement_dual_source_2026H1.json` 中的 `annual_snapshot` 是第12批最终88份原件生产回执的海螺行与其既有公告元数据无损组装，保留原五项金额、三表检查和原件指纹；它不是本次新的完整PDF解析。fixture另保留原公开源记录、获取时间、原文页文本及回执/原公开响应SHA。

公开源两项值恰与后续重述比较值相等，但其 `NOTICE_DATE/UPDATE_DATE` 仍为2026-03-25，不证明供应商使用何份文档或何时入库。保存后的解释仍仅做内部一致性检查，不重新读取当前登记、联网或宣称证据认证。人工财务确认仍为0。

`tests/test_conch_restatement_evidence.py` 检查真实两源单元格、原因页、千元/国际准则排除、生产比较及人工状态不变、六维精确匹配、双源上下文缺失/错配、禁止后续before、独立单位换算、元级微小差异、旧登记兼容和历史离线显示。专属UI回归由 `tests/test_conch_restatement_display.py` 覆盖。
