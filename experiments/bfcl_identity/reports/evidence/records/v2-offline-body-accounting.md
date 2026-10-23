# Frozen offline body accounting

Source: work/v2-offline-frozen.json. All counts use o200k_base. These are body counts, excluding shared tools, system/developer messages and the next new query; they are not full API request counts. Raw body is canonical visible fields joined with newlines.

## Nine GPT first-turn conditions

| Model | Task | Raw | Compact | Readable | Readable minus raw | <=150 |
|---|---|---:|---:|---:|---:|---|
| gpt-4.1 | base_3 | 151 | 874 | 197 | 46 | True |
| gpt-4.1 | long_context_3 | 155 | 878 | 201 | 46 | True |
| gpt-4.1 | base_12 | 100 | 1726 | 224 | 124 | True |
| gpt-4.1 | long_context_12 | 490 | 7479 | 653 | 163 | False |
| gpt-5-mini | base_16 | 358 | 3734 | 595 | 237 | False |
| gpt-5-mini | long_context_29 | 108 | 1798 | 226 | 118 | True |
| gpt-5-mini | long_context_39 | 85 | 1061 | 147 | 62 | True |
| gpt-5-mini | base_12 | 96 | 1910 | 236 | 140 | True |
| gpt-5-mini | long_context_12 | 451 | 7334 | 598 | 147 | True |

## Nine unique archived history1000 prefixes

The two model tokenizer labels resolve to the same o200k_base encoding and their rows were checked identical. Count each archived prefix once. No Qwen inference was run. The first-turn 150-token target does not apply to these longer prefixes.

| Task | Raw | Compact | Readable | Readable minus raw | Overhead % |
|---|---:|---:|---:|---:|---:|
| long_context_3 | 1379 | 11295 | 1685 | 306 | 22.19% |
| long_context_6 | 1077 | 10683 | 1448 | 371 | 34.45% |
| long_context_9 | 1322 | 10543 | 1592 | 270 | 20.42% |
| long_context_10 | 1082 | 11614 | 1904 | 822 | 75.97% |
| long_context_16 | 1257 | 9478 | 1467 | 210 | 16.71% |
| long_context_25 | 1662 | 4662 | 1865 | 203 | 12.21% |
| long_context_26 | 1760 | 12244 | 2062 | 302 | 17.16% |
| long_context_37 | 1509 | 10784 | 2123 | 614 | 40.69% |
| long_context_38 | 985 | 10779 | 1261 | 276 | 28.02% |

## Aggregate descriptive statistics

GPT first-turn: raw=1994; compact=26794; readable=3077. Ratio-of-sums overhead=54.31%; saving relative to compact=88.52%. Delta min/median/mean/max=46/124/120.33/237.

Archived history1000 unique prefixes: raw=12033; compact=92082; readable=15407. Ratio-of-sums overhead=28.04%; saving relative to compact=83.27%. Delta min/median/mean/max=203/302/374.89/822.

## Remaining overhead

- GPT-4.1 long_context_12: +163 = header 13 + state 53 + labels 97; five calls. The first-turn target is exceeded by 13 tokens.
- GPT-5-mini base_16: +237 = header 13 + state 63 + labels 161; nine calls. The labels alone exceed 150; target exceeded by 87.
- Archived long_context_10: +822; state 472 and labels 337 dominate. Fifteen calls. Detailed state content was not inspected in this report, so no stronger causal claim is made.
- Archived long_context_37: +614; labels 577, state 24, header 13. Thirty-four calls. The observed overhead is dominated by event framing, not state index size.
- Section-token counts are diagnostic. Full-body delta is authoritative; tokenizer boundary effects can make sums differ (e.g. archived long_context_6).

These checks support visible-field preservation and much lower representation overhead relative to compact. They do not establish semantic equivalence, recovered success rate, lower end-to-end token use, or a new Qwen experiment.
