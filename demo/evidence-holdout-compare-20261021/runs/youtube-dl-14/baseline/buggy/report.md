# GitHub 仓库代码审查报告

- 仓库：local-benchmark
- 分支：blinded-snapshot
- Commit：`snapshot`
- 状态：**partial**；模式：evidence；模型：deepseek-flash
- 完成语义审查：0/819 个已索引 Python 文件
- 调用：4；耗时：11.674 秒

## 范围与限制

- BugsInPy定范围评测：使用参考补丁选择代码窗口，Agent未看到补丁、测试、标签或另一版本。
- completed仅表示所选窗口及复核完成；完整文件审查数为0，不表示全仓库或全文件审查。
- 修复版本可能含其他缺陷；额外发现不自动计为误报。
- evidence模式使用Agent自行生成的测试与隔离执行，契约语义仍由模型核验；官方回归测试不提供给Agent。

## 已复现缺陷（0）

正式缺陷附测试与运行证据；其余候选和静态建议单列，不表示已经证实。

## 待验证候选与静态建议

### [中] 章节结束时间使用原始索引而非过滤后的上一章节

- 位置：`youtube_dl/extractor/youtube.py:1672`
- 来源：llm
- 复核：待验证 — 尚未复核；未运行待审代码。
- 问题：循环用 enumerate(chapter_lines, start=1) 的 next_num 判断是否为最后一行，但循环体内存在 continue（start_time 为 None、end_time 为 None）和 break。当某个中间章节因 parse_duration 返回 None 被 continue 跳过时，后续章节的 end_time 仍取 chapter_lines[next_num][1]，即原始列表的下一行，而不是实际被加入的下一章节。这本身与“下一行”语义一致，但若被跳过的行恰是最后一行，则 next_num == len(chapter_lines) 成立，end_time 取 duration，而实际最后加入的章节的 end_time 应为被跳过行的解析结果（None 则跳过该章节）。更明确的问题：当某章节 start_time > duration 触发 break 时，前面已加入的最后一个章节的 end_time 已被设为该越界章节的 start_time（因为 next_num 指向它），随后被 clamp 到 duration，行为可接受。真正缺陷在于 continue 分支：若 chapter_lines[next_num][1] 解析失败，当前章节被 continue 跳过，但其 start_time 已用于前一章节的 end_time，导致前一章节 end_time 指向一个未加入章节的时间点，章节区间出现空洞或重叠。
- 触发条件：description 含三行章节，第二行时间点无法被 parse_duration 解析（如 '1:2:3:4' 或空），第一行 start_time 有效。
- 依据：1667-1675：start_time 解析失败 continue；end_time = parse_duration(chapter_lines[next_num][1])，next_num 为原始索引；若该值为 None 则当前章节 continue，但前一章节已用该值作为 end_time。
- 修复建议：先过滤出可解析的章节列表，再基于过滤后的相邻元素计算 end_time，或解析失败时回退到 duration/下一有效时间点。
- 验证方式：候选缺陷描述的是章节区间在解析失败时可能出现空洞/重叠，但代码中没有任何文档、测试或语言规则约定 _extract_chapters 在中间章节时间点无法解析时必须如何计算相邻章节的 end_time。现有实现（跳过无法解析的章节、用原始下一行时间点作为 end_time）本身不能证明期望行为；候选建议的“先过滤再计算”只是改进建议，不是可定位的契约。因此无法构造有来源断言的复现测试。

```python
1670:             if start_time > duration:
1671:                 break
1672:             end_time = (duration if next_num == len(chapter_lines)
1673:                         else parse_duration(chapter_lines[next_num][1]))
1674:             if end_time is None:
1675:                 continue
```

- 复现状态：unsupported
- 证据说明：候选缺陷描述的是章节区间在解析失败时可能出现空洞/重叠，但代码中没有任何文档、测试或语言规则约定 _extract_chapters 在中间章节时间点无法解析时必须如何计算相邻章节的 end_time。现有实现（跳过无法解析的章节、用原始下一行时间点作为 end_time）本身不能证明期望行为；候选建议的“先过滤再计算”只是改进建议，不是可定位的契约。因此无法构造有来源断言的复现测试。

[运行证据](evidence/7e441a16cb1b/evidence.json)

### [中] DASH 签名解密异常未被捕获，导致整个提取失败

- 位置：`youtube_dl/extractor/youtube.py:2340`
- 来源：llm
- 复核：待验证 — 尚未复核；未运行待审代码。
- 问题：decrypt_sig 回调调用 self._decrypt_signature，而 _decrypt_signature 在 player_url 为 None 时抛 ExtractorError，在签名提取失败时也抛 ExtractorError（1408-1430 行）。re.sub 在 2340 行执行该回调，异常会从 re.sub 抛出。外层 try 只捕获 (ExtractorError, KeyError) 并 report_warning，看似覆盖，但注意 dash_mpd_fatal 初始为 True 且 _extract_mpd_formats 的 fatal 参数只影响其内部；re.sub 抛出的 ExtractorError 确实会被 2356 行捕获。真正的问题是：当第一个 manifest 解密失败被捕获后，dash_mpd_fatal 仍为 True，后续 manifest 的 _extract_mpd_formats 失败会以 fatal 方式抛出，但该异常同样被捕获。因此此处不构成崩溃。
- 触发条件：mpd_url 含 /s/<sig> 且 player_url 为 None。
- 依据：2335-2340 行 decrypt_sig 调用 _decrypt_signature；1408-1409 行 player_url 为 None 时 raise ExtractorError；2356 行 except (ExtractorError, KeyError) 捕获。
- 修复建议：无需修改；异常已被捕获并降级为警告。
- 验证方式：候选缺陷自身结论即为“无需修改；异常已被捕获并降级为警告”。静态检查确认：第2340行 re.sub 回调抛出的 ExtractorError 会被第2356行 except (ExtractorError, KeyError) 捕获并 report_warning，不会导致整个提取失败。因此不存在可复现的行为缺陷，无法构造有契约依据的失败测试。

```python
2338:                         return '/signature/%s' % dec_s
2339: 
2340:                     mpd_url = re.sub(r'/s/([a-fA-F0-9\.]+)', decrypt_sig, mpd_url)
2341: 
2342:                     for df in self._extract_mpd_formats(
2343:                             mpd_url, video_id, fatal=dash_mpd_fatal,
2344:                             formats_dict=self._formats):
2345:                         if not df.get('filesize'):
2346:                             df['filesize'] = _extract_filesize(df['url'])
2347:                         # Do not overwrite DASH format found in some previous DASH manifest
2348:                         if df['format_id'] not in dash_formats:
2349:                             dash_formats[df['format_id']] = df
2350:                         # Additional DASH manifests may end up in HTTP Error 403 therefore
2351:                         # allow them to fail without bug report message if we already have
2352:                         # some DASH manifest succeeded. This is temporary workaround to reduce
2353:                         # burst of bug reports until we figure out the reason and whether it
2354:                         # can be fixed at all.
2355:                         dash_mpd_fatal = False
```

- 复现状态：unsupported
- 证据说明：候选缺陷自身结论即为“无需修改；异常已被捕获并降级为警告”。静态检查确认：第2340行 re.sub 回调抛出的 ExtractorError 会被第2356行 except (ExtractorError, KeyError) 捕获并 report_warning，不会导致整个提取失败。因此不存在可复现的行为缺陷，无法构造有契约依据的失败测试。

[运行证据](evidence/7337254b3642/evidence.json)

## 覆盖范围

| 文件 | 静态检查 | 语义审查 | 完成分块 |
|---|---|---|---|
| youtube_dl/extractor/youtube.py | completed | window_completed | 2/2 |

## 失败记录

```json
[]
```

## 驳回的问题（0）


## 跳过文件

{"unsupported_language_or_resource": 74, "sensitive_file": 1, "benchmark_tests_hidden": 31}

逐文件跳过原因、模型调用用量和复核轨迹见 report.json / run.json。
