# 第15批完整年报范围（2026-09-25）

**2026-09-25 第15批开发验收范围：** 180份精确完整PDF、164家公司、178个公司／年度组合；
164份生成待人工复核候选，16份保留缺口，150家公司至少有一份候选。
本批新增48家公司2025年报，其中41份候选、7份缺口。
旧132份中131份状态、三表检查和两期五项原值、单位与页码保持；中国联通同一SHA原件恢复为候选，未新增原件计数。
中兴通讯既有金额不变，新增两处附注列读取记录。人工财务确认仍为0。可搜索股票数不等于完整年报验证数，未测试公司、年度、版本不推定成功。

本批支持有界附注列、跨页利润科目、明确亏损标签、拆行人民币单位，以及可核实结构冲突的PDF原生文字读取。
联通仅物理77–79页使用原生字形；默认文字、读取结果、两份文字哈希及PDF结构证据均保留，未OCR。
国航用报告期定义、法定名称/A股代码、完整年度财务封面及三表交叉核实身份，证据绑定原件SHA；
其物理79页股东权益续表为图像，仍无法通过三表检查，五项标准化金额保持待核验。
不能把年度身份通过当作财务核对通过，也不借其他版本、公开源或公式填补空白。

新增240项公开金额对照：203项零差额、2项保留差异、35项不可比。
通化东宝总资产和总负债差异分别为-45,345,763.41元、-43,693,145.27元（年报减公开源）；原因未核实，继续待人工复核。
完整本地测试3,861项通过；原文件、初测失败和后续修复分别保留。
手工32 MiB、官方45 MiB、1000页和8M文字上限保持，生产串行解析与原生缓存清理保持。

详细范围见[第15批完整年报](INDUSTRY_EXPANSION_15.md)、[读取与身份依据](COVERAGE15_READING_EVIDENCE.md)。
前序成果见[第14批](INDUSTRY_EXPANSION_14.md)、[官方原件入口](TESTED_ORIGINAL_SNAPSHOT.md)。
本地验收与线上部署分别记录；实际线上版本以 `/app/static/release.json` 和对应发布回执为准。


## 新增48份原件

| 公司 | 公告日 | PDF页数 | 本次状态 | 官方原件 | SHA-256 |
|---|---|---:|---|---|---|
| 002463 沪电股份 | 2026-03-25 | 196 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-25/1225027832.PDF) | `9810736ee50d0fa7f4d8e8370e3965bde8e24c6dbafb86593ae2206b0e2f2f15` |
| 002916 深南电路 | 2026-03-13 | 200 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-13/1225006760.PDF) | `80c2d67323e64875eb80d7f13603930bc0a5087631ebbd66f14c109bada627d9` |
| 300476 胜宏科技 | 2026-03-13 | 230 | 保留缺口 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-13/1225007455.PDF) | `2d13d1746e8a6fda8960201f8d5dc759de19f650d2b5db4a5c8082d5df197099` |
| 300408 三环集团 | 2026-03-28 | 160 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-28/1225041594.PDF) | `4f2da7d6c5905c053237981fd4e01b834c5df99ae00fe65fd14fee13436220e6` |
| 002384 东山精密 | 2026-04-22 | 167 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-22/1225139318.PDF) | `fe246facade2909e87dafb8d3f027789491fb541714a57bffce0fb6b7fabc9e3` |
| 002600 领益智造 | 2026-03-28 | 390 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-28/1225043467.PDF) | `fbd2c1054042aa2176af2cfc9c94363cc417e220da1e903a9f0b8f5c40438e2f` |
| 002456 欧菲光 | 2026-04-02 | 240 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-02/1225073292.PDF) | `f6347ccf388e116d26bf8c790ec09a2f34b8d05170d2fc753e386b4c0289e11e` |
| 002938 鹏鼎控股 | 2026-03-31 | 196 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-31/1225062281.PDF) | `a4a9c9c02f8486c46ff0d1dcf5e28ee62a951e4f4b22cf0eb5176082dca624da` |
| 300433 蓝思科技 | 2026-03-31 | 249 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-31/1225064958.pdf) | `ea4076377c5ce01c986cddaf65f32beb6db5a07c983c86a83ceb014c104ac521` |
| 300661 圣邦股份 | 2026-03-28 | 174 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-28/1225045012.PDF) | `2c6cc2667b3b736d22d7274f5e8903d8e4b880656639f5679978e1e10974a38f` |
| 300782 卓胜微 | 2026-04-28 | 179 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-28/1225220151.PDF) | `68c62c09d5eb4ede2a43d77308943439b8ba82d428f278f7b72b2168d88b001c` |
| 300223 君正股份 | 2026-03-28 | 206 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-28/1225045085.PDF) | `8dbeb6fb2eab282c3120ea8a00dda095c161714e896e87a74cda312e2546e5eb` |
| 300458 全志科技 | 2026-03-27 | 192 | 保留缺口 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-27/1225035756.PDF) | `d5e7fd64589c08a69734650fbc14376d9c412d2b13b75c2eb486a89efc76f889` |
| 300604 长川科技 | 2026-04-25 | 244 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-25/1225193261.PDF) | `eecb3880920986d87b304aa8ca894dbbfd249ac035274d4c38fd2e8cbf65fe91` |
| 300567 精测电子 | 2026-04-28 | 253 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-28/1225201722.PDF) | `9ef5fd1981452067cec30a69dae336f0c2aa7e7d7105aeb4e819f05c99c0a32b` |
| 300450 先导智能 | 2026-03-31 | 206 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-31/1225058761.PDF) | `7ee3a049530870530cd0a0faab7ec6fa8ed0811e753bb27cb67b61cac0de9cda` |
| 300014 亿纬锂能 | 2026-03-28 | 222 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-28/1225045391.PDF) | `3bee0ca9a6232c60c53f195d078446a45fd4941bd997258b474cebe835eea3b8` |
| 002812 恩捷股份 | 2026-04-23 | 212 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-23/1225148267.PDF) | `99206da4fa5fe3aea264af0e17b41dc69a2cdaa1292ecd6f1d61927eb347f685` |
| 002709 天赐材料 | 2026-03-10 | 199 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-10/1225002090.PDF) | `81877607987489f2454c2128180e0427ad871e44f8cbc9fe3d3e931776b8e4a3` |
| 300073 当升科技 | 2026-03-31 | 205 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-31/1225057127.PDF) | `48d7ebcf4c26e46dc267b3a773d1a47637e6230d68df65ec537552b795bd5cce` |
| 300316 晶盛机电 | 2026-04-11 | 159 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-11/1225095476.PDF) | `12e7e79eea6589b461b1b1030a2cf2e00257dba8051d9491200469b837317163` |
| 002920 德赛西威 | 2026-03-06 | 210 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-06/1224998406.PDF) | `5c57c31d09f39410f29e77e8ff79aa6e0a4e790ef19807ac7e1c528ef3968142` |
| 002472 双环传动 | 2026-04-24 | 175 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-24/1225170753.PDF) | `c8f160f3e18d3862cdcafab7aa898ec3b0c7ce2a2685cbfeb8734af4c04c045a` |
| 002126 银轮股份 | 2026-04-15 | 243 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-15/1225103385.pdf) | `7ffd9539c0939203963fa1e7cc43540bee489ebd72c90a4bc8d35816a19f93b6` |
| 600809 山西汾酒 | 2026-04-23 | 169 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-23/1225156714.PDF) | `f824fbe77c0bf415d14b55fe951cc9fa27e326d700535d70e03a4ee009d47e6a` |
| 600779 水井坊 | 2026-04-30 | 192 | 保留缺口 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-30/1225259544.PDF) | `e4e0e9a8fa33924cd7318aa1bbd181305490d4932af9a2cd0a8c94f4f4098cb8` |
| 600872 中炬高新 | 2026-04-18 | 193 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-18/1225123413.PDF) | `b35d3459385f625fdac34a443817cf3db2a30dce989a560e7158f62ec3e441b5` |
| 603369 今世缘 | 2026-04-29 | 166 | 保留缺口 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-29/1225245218.PDF) | `837871f1ce9300beec0e3de41a72ba5439f53acf8193ae7927e5901baf24db5f` |
| 603027 千禾味业 | 2026-04-30 | 190 | 保留缺口 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-30/1225262172.PDF) | `a141b36459963b375510c651298135240c76967041ce78f0d607a19b27b763bd` |
| 600305 恒顺醋业 | 2026-04-15 | 299 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-15/1225103121.PDF) | `e3f51d6521de8b340cb98b774b6b255e5397e565ea3a3599f1e7f5bfe22ecd91` |
| 600597 光明乳业 | 2026-03-31 | 203 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-31/1225052071.PDF) | `03b4e2fa01dce9242849f28ee20a4b3d7f480cf4c86959ec60f45794d46be24a` |
| 600066 宇通客车 | 2026-03-31 | 139 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-31/1225050742.PDF) | `9ae45f75fa60d2f17099b4add32690e3443e6c6eba3da3e24d91c9213fdb11a9` |
| 600487 亨通光电 | 2026-04-25 | 329 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-25/1225195764.PDF) | `249217ed39e5cb1485322562fe9ae9cc0a5b609cbe3d867ef873095a3d717e7b` |
| 600498 烽火通信 | 2026-04-25 | 201 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-25/1225178004.PDF) | `b2db3ba847b9a8fd8aa27afb8754add75949e41e0f302e9babe6dfb528917545` |
| 600563 法拉电子 | 2026-03-28 | 133 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-28/1225040778.PDF) | `9c70b0deb814d4c8b9c7dfba8e5135358c2970c607ad9223a9b49a8109cac120` |
| 600196 复星医药 | 2026-03-25 | 318 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-25/1225028389.PDF) | `304c0b809fe459a7a7b5784d31b5facc12d9ff7152423a9ce5c8df5efbea1aff` |
| 600436 片仔癀 | 2026-04-30 | 300 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-30/1225263103.PDF) | `7f63ecd028329cf48acebf5e256d227ee5ea02fe839a1f1ddeec7c0c557e002e` |
| 600332 白云山 | 2026-03-21 | 317 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-21/1225023763.PDF) | `aca5ef257cfc8ab8fb7742c25d4e5a0e31872834c4906d37bbd179ab9758663b` |
| 600079 ST人福 | 2026-03-31 | 252 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-31/1225050708.PDF) | `41e08d614d08a1baaa7b7e1fe33d10592fe17b46301f09a946f336ea82334466` |
| 600867 通化东宝 | 2026-04-20 | 232 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-20/1225123926.PDF) | `900a951ffda575622dd67fe8489e32fd366c2d2a8ab4a176ef1d0eb1a5a65ad7` |
| 600161 天坛生物 | 2026-03-28 | 222 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-28/1225042495.PDF) | `775a7d6f736aec5e42f5caa8fa139a9d6c39bcdd78c93d57570cab5a550f669f` |
| 601991 大唐发电 | 2026-03-28 | 284 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-28/1225046476.PDF) | `0e6beb6236b889683321f562f261d2a11b4e405a1601463c5387c24befd92b8c` |
| 600674 川投能源 | 2026-04-18 | 249 | 保留缺口 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-18/1225117474.PDF) | `f14725f59af1b0621157675d645c784f8117fc3eb85f5b7257f3875ba5f75dfa` |
| 600350 山东高速 | 2026-04-04 | 417 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-04/1225079916.PDF) | `2cac1cada850d326f778dc261f45aee8ce9a8134268ecee19ee3da7586ef8059` |
| 601872 招商轮船 | 2026-03-27 | 246 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-27/1225037458.PDF) | `3fe6f99980f9f0c2ac241e2f826660141d118af2fe53eafab49e146ef9464a18` |
| 601111 中国国航 | 2026-03-27 | 216 | 保留缺口 | [PDF](https://static.cninfo.com.cn/finalpage/2026-03-27/1225039287.PDF) | `cb4637907c8edd85349a72e86e65c1b4581c42b17c69a4c5c6a88a15ea3c63ec` |
| 600885 宏发股份 | 2026-04-02 | 225 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-02/1225071093.PDF) | `aa43f25ae68d1f4fd15a42bb4e4c2f9db51615832370c5e07bf03541b1d1c590` |
| 603899 晨光股份 | 2026-04-01 | 217 | 待人工复核候选 | [PDF](https://static.cninfo.com.cn/finalpage/2026-04-01/1225069140.PDF) | `2ac6b67f156167c5d791d8b2ea5890ad0bbdad6382954c0644b63360b9c7010a` |

## 保留的缺口

新增胜宏科技、全志科技、今世缘、千禾味业存在少数股东损益空白；水井坊同时有少数股东损益和汇率现金行空白；川投能源汇率现金行空白；国航股东权益续页为图像。空白不能推定为零。
旧原件除中国联通外的九个缺口保持；国投电力约74.15 MiB仍超过官方45 MiB上限，未计入这180份分母。
君正股份300223是原北京君正，当前更名与年报原名分别保留，股票代码未改变。

## 原件与测试边界

48新增原件初测36候选、11缺口、1身份拒绝，最终结果另存。所有原件SHA、公告日期、物理页数和两期金额按真实文件记录；不把视觉开发核查写成用户财务确认。
经营利润分项增强检查仍只支持已验证版式；三表指定关系通过不等于整张利润表、全部会计处理或审计意见均已验证。
