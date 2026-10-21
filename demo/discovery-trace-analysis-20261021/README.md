# P1 轨迹分析：候选发现失败在“发现”还是“晋升/机制选择”（2026-10-21）

**范围：离线分析，0 次模型调用、0 次 Docker。** 输入是 P1/P1b/P1c/P1d/P1e 的冻结 `results.json`/`adjudications.json`，不是新实验。P1 账本已用满 80/80。

## 为什么要做

P1 系列逐轮改进了“工具执行/读取对象”，但候选召回没有提高。为了决定下一步，需要区分三种失败：

1. **发现缺口**：参考概念根本没有进入模型的 reasoning；
2. **晋升缺口**：参考概念/假设已经在 reasoning 中，但没有被写成 finding；
3. **机制精度缺口**：候选提到了参考概念，但选了一个不同的机制/触发条件。

## 结果

| 样本 | 分类 | reasoning 有参考概念？ | findings 命中？ | 候选命中？ | 关键证据 |
|---|---|---|---|---|---|
| youtube-dl-4 | **hit** | baseline 无 hypothesis | 是 | 是 | P1 baseline e95589a418cc 明确说 regex 要求非空、`f()` 不匹配 |
| youtube-dl-2 | **promotion_gap** | 是（P1/P1d） | 否 | 否 | P1 hypothesis #4 已写 `existing_format.update(f)` 重复 `representation_id` 覆盖 fragments，并给具体反例；最终只输出 SegmentTimeline/ISM |
| tornado-3 | **precision_gap** | 是 | 部分 | 否 | 提到 instance_cache/close/cache/weak，但候选是 `__new__` 初始化/fetch headers，不是“已清理 weak entry 后 close” |
| tornado-7 | **precision_gap** | 是 | 部分 | 否 | 提到 Future/run_in_executor，但候选是 `_discard_future_result` 异常和 `set_default_executor(None)`，不是 concurrent.futures.Future 不能被原生 async await |
| youtube-dl-8 | **precision_gap** | 是 | 部分 | 否 | 提到 filter/current_selector/pickfirst，但候选是未闭合 `[`/缺失左侧选择器，不是 `'/'` fallback 清空 current_selector 后 filters 丢失 |
| tornado-1 | **discovery_gap** | 仅泛提 ws_connection | 否 | 否 | 没有把 `set_nodelay` 的 `self.stream` 与 `ws_connection` 冲突写成候选 |

计数：6 个样本中 **1 个 hit、1 个 promotion_gap、3 个 precision_gap、1 个 discovery_gap**。

## 结论

- **主要瓶颈不是“没有工具/没有外部读取”**：P1c/P1d 已经证明工具和外部 caller/callee 都能真实执行，但候选仍偏。
- **4/5 个漏检样本的参考概念或邻近机制已经出现在 reasoning/findings 中**，模型选了另一个机制；最常见的是“邻近问题替代了参考问题”。
- youtube-dl-2 是最干净的 **promotion gap**：假设已经正确、反例已经具体，但没有晋升为 finding。
- P1e 的“完整性审计”只检查“有没有漏掉的 hypothesis”，没有做 **候选机制比较/替换**，所以没有触及 precision_gap；而且 P1e 这次没有复现 P1 的前提，结论不确定。

## 下一步协议草案（尚未运行，需要新预算）

**P2：候选机制/排序审计（mechanism/ranking audit）**，仍只改一个变量：

1. 第一轮照常产生 hypotheses/findings；
2. 第二轮审计不只看“漏没漏”，而是对每条 finding 要求：
   - 它实现的是哪条 hypothesis；
   - 该 hypothesis 的具体反例是什么；
   - 是否存在另一条 hypothesis，反例更具体、契约违反更直接，却没有进入 findings；
   - 如果存在，**替换**较弱/邻近的 finding，而不是简单追加。
3. 审计提示中**不出现参考标签/参考问题文本**，只使用模型自己的 hypotheses 和代码；
4. 建议样本：youtube-dl-2（promotion）+ tornado-3 或 youtube-dl-8（precision）；每臂 2–4 窗口；
5. 新账本建议上限 20–24 次，先 smoke，只有候选命中提高且固定侧告警不增加才扩展；
6. 仍保留所有初始/审计请求、失败和冻结源码。

这个协议直接针对本报告的最大类别（1 个 promotion + 3 个 precision），比继续改工具协议更贴近证据。**在用户确认方向和预算前，不启动。**

## 复现

```bash
PYTHONPATH= .venv/bin/python demo/discovery-trace-analysis-20261021/verify.py
```

校验脚本只读冻结文件，核对计数、P1 youtube-dl-4 的 hit、youtube-dl-2 的未命中、P1e 前提未复现，以及输入哈希。

## 限制

- 关键词匹配只是筛查；候选命中以冻结判读为准。
- 单次重复，模型波动大；P1e 没有复现 P1 的 youtube-dl-2 假设就是例子。
- 这是离线分析，不是新的召回率结果；没有 holdout，不宣称提升。
