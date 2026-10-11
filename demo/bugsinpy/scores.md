# BugsInPy 参考问题评分

只统计审查完整、成对复现成功且有语义判读的样本。所有排除项见 scores.json。

| 模式 | 有效/计划缺陷对 | 已知缺陷检出 | 修复后同问题误报 | 成对区分正确 |
|---|---|---:|---:|---:|
| direct | 18/20 | 4 | 0 | 4 |
| full | 19/20 | 3 | 0 | 3 |

判读者：Codex model-assisted evidence review; human review pending

这些是限定窗口、限定参考缺陷的结果，不能解释为全仓库精确率；模型辅助判读仍需人类复查。
