# BugsInPy 定范围审查评测

Agent 未获得缺陷标签、修复补丁、测试或另一版本。窗口位置由参考补丁确定；结果不代表全仓库检测能力。

修复版本可能仍有其他问题。修复后对同一个参考问题的报告才算该问题的误报；额外候选需要独立判断。

| 样本 | 模式 | 版本 | 审查状态 | 复现 | 调用 | 耗时(s) | 候选数 |
|---|---|---|---|---|---:|---:|---:|
| PySnooper-1 | direct | buggy | completed | reproduced | 3 | 11.929 | 9 |
| PySnooper-1 | direct | fixed | partial | reproduced | 3 | 12.653 | 5 |
| PySnooper-1 | full | buggy | completed | reproduced | 8 | 32.527 | 4 |
| PySnooper-1 | full | fixed | completed | reproduced | 9 | 31.013 | 7 |
| tornado-1 | direct | buggy | completed | reproduced | 3 | 15.364 | 8 |
| tornado-1 | direct | fixed | completed | reproduced | 3 | 15.807 | 7 |
| tornado-1 | full | buggy | completed | reproduced | 11 | 31.61 | 3 |
| tornado-1 | full | fixed | completed | reproduced | 10 | 29.878 | 2 |
| youtube-dl-1 | direct | buggy | completed | reproduced | 1 | 12.827 | 6 |
| youtube-dl-1 | direct | fixed | completed | reproduced | 1 | 8.641 | 6 |
| youtube-dl-1 | full | buggy | completed | reproduced | 4 | 14.878 | 1 |
| youtube-dl-1 | full | fixed | completed | reproduced | 4 | 13.585 | 1 |
| PySnooper-2 | direct | buggy | completed | not_reproduced | 5 | 23.54 | 16 |
| PySnooper-2 | direct | fixed | completed | not_reproduced | 5 | 22.963 | 15 |
| PySnooper-2 | full | buggy | completed | not_reproduced | 15 | 39.736 | 5 |
| PySnooper-2 | full | fixed | completed | not_reproduced | 17 | 49.154 | 9 |
| tornado-2 | direct | buggy | completed | reproduced | 1 | 5.25 | 3 |
| tornado-2 | direct | fixed | completed | reproduced | 1 | 1.106 | 0 |
| tornado-2 | full | buggy | completed | reproduced | 4 | 14.507 | 1 |
| tornado-2 | full | fixed | completed | reproduced | 3 | 11.993 | 1 |
| youtube-dl-2 | direct | buggy | completed | reproduced | 1 | 1.356 | 0 |
| youtube-dl-2 | direct | fixed | completed | reproduced | 1 | 1.494 | 0 |
| youtube-dl-2 | full | buggy | completed | reproduced | 3 | 9.415 | 3 |
| youtube-dl-2 | full | fixed | completed | reproduced | 3 | 9.385 | 6 |
| PySnooper-3 | direct | buggy | completed | reproduced | 1 | 3.522 | 2 |
| PySnooper-3 | direct | fixed | completed | reproduced | 1 | 3.613 | 3 |
| PySnooper-3 | full | buggy | completed | reproduced | 4 | 7.398 | 2 |
| PySnooper-3 | full | fixed | completed | reproduced | 4 | 9.157 | 2 |
| tornado-3 | direct | buggy | completed | reproduced | 1 | 1.512 | 0 |
| tornado-3 | direct | fixed | completed | reproduced | 1 | 0.905 | 0 |
| tornado-3 | full | buggy | completed | reproduced | 3 | 8.128 | 1 |
| tornado-3 | full | fixed | completed | reproduced | 4 | 8.677 | 0 |
| youtube-dl-3 | direct | buggy | completed | reproduced | 1 | 5.991 | 5 |
| youtube-dl-3 | direct | fixed | completed | reproduced | 1 | 7.739 | 6 |
| youtube-dl-3 | full | buggy | completed | reproduced | 4 | 11.053 | 4 |
| youtube-dl-3 | full | fixed | completed | reproduced | 4 | 11.801 | 1 |
| tornado-4 | direct | buggy | completed | reproduced | 1 | 6.369 | 4 |
| tornado-4 | direct | fixed | completed | reproduced | 1 | 5.281 | 3 |
| tornado-4 | full | buggy | completed | reproduced | 3 | 5.389 | 0 |
| tornado-4 | full | fixed | completed | reproduced | 4 | 8.863 | 0 |
| youtube-dl-4 | direct | buggy | completed | reproduced | 1 | 7.145 | 6 |
| youtube-dl-4 | direct | fixed | completed | reproduced | 1 | 6.481 | 6 |
| youtube-dl-4 | full | buggy | completed | reproduced | 5 | 18.077 | 1 |
| youtube-dl-4 | full | fixed | completed | reproduced | 5 | 16.856 | 0 |
| tornado-5 | direct | buggy | completed | reproduced | 1 | 6.284 | 4 |
| tornado-5 | direct | fixed | completed | reproduced | 1 | 1.459 | 0 |
| tornado-5 | full | buggy | completed | reproduced | 3 | 10.075 | 0 |
| tornado-5 | full | fixed | completed | reproduced | 3 | 14.961 | 1 |
| youtube-dl-5 | direct | buggy | completed | reproduced | 1 | 13.07 | 6 |
| youtube-dl-5 | direct | fixed | completed | reproduced | 1 | 12.132 | 6 |
| youtube-dl-5 | full | buggy | completed | reproduced | 4 | 17.28 | 5 |
| youtube-dl-5 | full | fixed | completed | reproduced | 4 | 12.769 | 4 |
| tornado-6 | direct | buggy | completed | reproduced | 3 | 6.823 | 4 |
| tornado-6 | direct | fixed | completed | reproduced | 3 | 2.537 | 0 |
| tornado-6 | full | buggy | completed | reproduced | 3 | 2.692 | 0 |
| tornado-6 | full | fixed | completed | reproduced | 3 | 3.725 | 0 |
| youtube-dl-6 | direct | buggy | completed | reproduced | 1 | 5.424 | 4 |
| youtube-dl-6 | direct | fixed | completed | reproduced | 1 | 8.309 | 5 |
| youtube-dl-6 | full | buggy | completed | reproduced | 3 | 12.063 | 4 |
| youtube-dl-6 | full | fixed | completed | reproduced | 3 | 11.492 | 4 |
| tornado-7 | direct | buggy | completed | reproduced | 2 | 2.468 | 0 |
| tornado-7 | direct | fixed | completed | reproduced | 2 | 1.781 | 0 |
| tornado-7 | full | buggy | completed | reproduced | 4 | 8.988 | 3 |
| tornado-7 | full | fixed | completed | reproduced | 5 | 11.396 | 1 |
| youtube-dl-7 | direct | buggy | completed | reproduced | 1 | 4.328 | 2 |
| youtube-dl-7 | direct | fixed | completed | reproduced | 1 | 6.837 | 4 |
| youtube-dl-7 | full | buggy | completed | reproduced | 3 | 9.331 | 0 |
| youtube-dl-7 | full | fixed | completed | reproduced | 3 | 9.75 | 4 |
| tornado-8 | direct | buggy | completed | reproduced | 1 | 0.857 | 0 |
| tornado-8 | direct | fixed | completed | reproduced | 1 | 1.183 | 0 |
| tornado-8 | full | buggy | completed | reproduced | 1 | 0.963 | 0 |
| tornado-8 | full | fixed | completed | reproduced | 1 | 2.285 | 0 |
| youtube-dl-8 | direct | buggy | completed | reproduced | 1 | 1.321 | 0 |
| youtube-dl-8 | direct | fixed | completed | reproduced | 1 | 6.572 | 5 |
| youtube-dl-8 | full | buggy | completed | reproduced | 4 | 12.509 | 4 |
| youtube-dl-8 | full | fixed | completed | reproduced | 4 | 12.206 | 6 |
| youtube-dl-9 | direct | buggy | completed | reproduced | 2 | 7.944 | 6 |
| youtube-dl-9 | direct | fixed | completed | reproduced | 2 | 6.985 | 5 |
| youtube-dl-9 | full | buggy | completed | reproduced | 5 | 13.777 | 5 |
| youtube-dl-9 | full | fixed | completed | reproduced | 6 | 15.232 | 5 |

总模型调用：257。

## 评分

自动位置重叠只用于筛选人工复查项。本批次的模型辅助判读及排除项见 [scores.md](scores.md)，完整候选和判读理由见 [adjudications.json](adjudications.json)。仍需人类复查。
