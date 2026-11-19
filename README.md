# nanopub-claim-builder · 论文结论 → 可核验的 Nanopublication 断言

面向「阅读14｜Nanopublication」：把论文里的**关键结论拆成一条条原子断言**（主体 - 关系 - 客体 + 条件/极性/语气/归属），为每条断言绑定**最小证据片段**
（页码、章节、bbox、逐字引文、字符偏移），记录**来源元数据及其出处**（题名/作者/年份/DOI/arXiv/版本/文件哈希），并导出**机器可读**的
nanopublication（TriG：Head / assertion / provenance / pubinfo 四个命名图）与 JSON / JSONL / CSV。

断言由模型阅读后撰写；凡是「必须确定、可以复核」的事情都交给脚本：证据单元化（`E012`、句级 `E012.3`）、**每条断言提交即核验**（引文是否逐字出自原文、
数字是否在所引证据里、主体/客体是否真的出现在证据中、关系方向与关系类型、是否原子、被丢掉的限定条件、过宽措辞、弱化/否定、断言属于本文还是被引文献、
证据是否最小、重复），导出文件按 Nanopublication 规范做合规校验，并检查每个证据定位都能还原引文。

> 文中数字都来自开发自测（4 篇真实论文上手写的 31 条断言 + 虚构示例论文 + 公开数据集 SciFact），**不是平台成绩**；断言由开发者本人撰写，
> 没有与「不加载 Skill 的模型」做过对照，因此不宣称相对基线的提升；未在评测模型（DeepSeek）和真实预算下实跑。

## 对应题面的四个问题
| 题面问题 | 做法 | 自查手段 |
|---|---|---|
| 拆得细 | 一条断言 = 一个主体 - 关系 - 客体（受控关系词表，27 个术语 + `other`）+ `cond`（条件/范围）+ `polarity` + `modality`；`atoms` 给出子句切分点、关系动词、实体候选、限定短语、数字、弱化/否定词、引用 | 并列关系动词/并列从句/过长/多量纲 → 非原子；代词主语、实体并列 → 提示 |
| 对得上 | 证据按单元/句子编址；引文必须逐字出现在所引单元；数字必须出现在证据里；主体客体必须出现在证据里；关系必须在证据中有措辞；与「最小充分句集」比较 | `quote_missing`、`numbers`、`entity_not_in_evidence`、`relation_type`（相关≠因果）、`evidence_not_minimal` |
| 追得回 | 每条证据：单元、句号、页码、bbox、章节路径、字符起止、前后文；来源文件 SHA-256；来源字段带出处与可信度；被引文献断言连到参考文献表（有 DOI 则给 DOI） | `assemble` 检查「定位能还原引文」；`origin: cited` 的断言写入 `prov:wasDerivedFrom <被引文献>` |
| 读得懂 | `nanopubs.trig`（四图结构 + `oa:TextQuoteSelector`）、`nanopubs.json/jsonl`、`claims.csv`、`result.json`；控制词表映射到 OBO 关系本体（已逐个在 OLS 查证） | `validate`：唯一 head 四元组、五个 IRI 互异、所有三元组在命名图内、provenance 引用 assertion、pubinfo 引用 nanopub；开发时用 rdflib 交叉验证 |

## 目录
```
SKILL.md                         Agent 入口：何时用、步骤、断言块格式、关系词表、检查规则、异常处理
README.md                        本文件
scripts/npb.py                   命令行：prepare / outline / read / find / candidates / atoms / meta / ingest / next / check / merge / drop / assemble / validate / search / status
scripts/claims.py                断言解析与核验（全部检查规则）
scripts/export.py                TriG / JSON / CSV 导出，TriG 合规校验器（纯标准库）
scripts/vocab.py                 关系词表、命名空间、标识符前缀、线索词
scripts/srcmeta.py               来源元数据、参考文献表解析、可选 Crossref 查询
scripts/units.py                 论文读取：PDF/docx/md/txt/tex/json → 证据单元、章节、锚点
scripts/nlib.py, parse_pdf.py    归一化/BM25/句子切分；PDF 解析（来自 scholarly-pdf-parser，含 OCR 接入）
references/                      字段字典、关系词表、检查规则（含实测）、故障处置、方法说明
examples/                        虚构示例论文、19 条断言（含 1 条 unsupported）、13 条故意写错的断言、真实运行输出 example_output/
GITHUB_URL.txt                   作品的 GitHub 公开链接
dev/ （仅仓库）                  植入缺陷评测、SciFact 评测、4 篇真实论文的断言样例与评测结果
```

## 依赖与安装
- Python 3.8+，断言流程只用标准库（已在系统 Python 3.9 上跑通 prepare → ingest → assemble → validate）。
- PDF 输入用自带 `scripts/parse_pdf.py`，需要 `pymupdf`（可回退 `pdfplumber` / `pypdf`）；扫描件需要 OCR：`pip install rapidocr`（中英文，模型已打包）或 `tesseract`。
- Markdown / 文本 / LaTeX / `.docx` / `.json` 无需额外依赖；也可直接用 `/input/case.json` 里的一段文字（`paragraph` / `text` 字段）。
- 运行时不联网（`meta --crossref` 可选）。开发环境 Python 3.11、pymupdf 2.1、rapidocr 3.10；开发期校验用 rdflib 7.6（不是运行依赖）。

## 使用步骤
```bash
python3 scripts/npb.py prepare paper.pdf --work W [--case /input/case.json]   # 解析、章节、来源元数据、参考文献
python3 scripts/npb.py candidates W                                          # 像关键结论的句子（排除已被断言覆盖的）
python3 scripts/npb.py atoms W E104.1 E105.1                                 # 拆分提示
python3 scripts/npb.py ingest W < claims.txt                                 # 提交断言，立即核验
python3 scripts/npb.py next W                                                # 还缺什么、哪些要修
python3 scripts/npb.py assemble W --out out --case /input/case.json          # 导出 + result.json
python3 scripts/npb.py validate out/nanopubs.trig                            # 规范校验
```
断言块格式（无需 JSON 转义）：
```
=== claim
text: 一句自足的断言。
s: 主体      p: outperforms      o: 客体
cond: 成立条件（数据集/物种/剂量/n/p 值/比较幅度）
ev: E104.1
quote: "从证据中逐字复制的最小片段"
polarity: negative            # 论文说「不成立」时使用
origin: cited                 # 断言属于被引文献时使用
```
完整示例（真实运行输出）见 `examples/minimal-example.md`，导出文件见 `examples/example_output/`。

## 输出
`nanopubs.trig` · `nanopubs.json` · `nanopubs.jsonl` · `claims.csv` · `source.json` · `evidence_index.json` · `review_checklist.md` · `check_report.json` ·
`result.json`（契约字段 + `case_id` + `status` + `sources` + `uncertainty` + `change_records`；推导不出的字段置 `null` 并列出，不编造）。
状态：`success`（有断言、无被拒断言、TriG 合规、定位可还原、来源字段齐）/ `partial` / `failed`。无法支撑的断言写 `status=unsupported` 并说明查找范围，不进入 TriG。

## 实测（开发自测，非平台成绩）
**植入缺陷**（`dev/seeded_claims_eval.py`）：Attention、BERT、ResNet、LIGO GW150914 四篇真实论文上手写 31 条正确断言（由开发者撰写，数字偏乐观），逐条植入一种缺陷，用与 `ingest` 相同的代码检测。
正确断言：错误级误报 0，10/31 带合理警告。

| 植入的缺陷 | 检出（任一提示） | 错误级检出 |
|---|---|---|
| 伪造引文（改两个词） / 释义冒充引文 | 100 % / 100 % | 100 % / 100 % |
| 锚点指到别的章节（带引文 / 无引文） | 100 % / 100 % | 100 % / 94 % |
| 数字被改 / 删掉证据锚点 | 100 % / 100 % | 100 % / 100 % |
| 两条断言拼成一条（复合断言） | 100 % | 100 % |
| 主体 / 客体被换成别处实体 | 79 % / 83 % | 72 % / 69 % |
| 正文被换成无关句子 | 90 % | 42 % |
| 极性翻转 | 97 % | 0 %（设计为警告） |
| 加入「in all cases, always」 | 100 % | 0 %（设计为警告） |
| 关系改成 `causes` / `treats`（相关→因果） | 77 % / 77 % | 0 %（设计为警告） |
| 主客体互换（方向错） | 71 % | 0 %（设计为警告） |
| 多余证据（非最小） | 100 % | 0 %（设计为警告） |
| 删除限定条件 | 19 %（条件常同时写在断言正文里，仅当证据含限定短语而断言里没有时触发） | 0 % |

**SciFact 公开数据集**（CC BY-NC 2.0，`dev/scifact_eval.py`）：772 个「断言-摘要」对（带专家标注的证据句）。从整篇摘要里提出最小证据句：首选句命中金标准证据句 32 %（随机 21 %、第一句 7 %），
提出的句集（2.0 句）覆盖 55 % 的金标准证据句（金标准平均 1.8 句，整篇摘要约 9.7 句）——这只是候选建议，作者自己的锚点优先。原子性：673 条单一断言里 3.3 % 被误报；300 条人工拼接的复合断言全部检出（含显式并列词，较容易；无并列词的复合断言不覆盖）。

## 已知限制
- 检查是规则式的：换了意思但沿用原文词汇的断言能通过词汇检查；关系方向依赖词序与被动标记；弱化/否定/限定短语依赖词表（语言线索为英文，引文/数字/锚点检查支持中文）。
- 实体对齐是词形级（支持 BERT-large = BERTLARGE），不解决同义词与别处定义的缩写；标识符只做语法检查，不联网解析。
- 来源元数据是启发式抽取（超长协作组作者名单会被概括；期刊行是原文片段）：每个值都带出处和可信度，需人工确认。
- nanopublication 未铸造/签名/发布，IRI 为占位前缀（`--base` 可改），无 trusty URI。
- 图片中的数字/公式不在文本层，无法绑定证据（标 `unclear`）；扫描件依赖 OCR。
- 未在评测模型（DeepSeek）和真实预算下实跑；请求数（约 12–18 次）是按流程推算，不是实测；未测多语言（英中之外）与含图片/文本框的 Word。

## 版本与维护
`npb.py` 1.0.0 · schema `np-claim-builder/1` · 问题与改进请在 GitHub 仓库提 issue。
