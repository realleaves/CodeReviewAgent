# GitHub 仓库代码审查报告

- 仓库：local-benchmark
- 分支：blinded-snapshot
- Commit：`snapshot`
- 状态：**partial**；模式：evidence；模型：deepseek-flash
- 完成语义审查：0/819 个已索引 Python 文件
- 调用：7；耗时：22.555 秒

## 范围与限制

- BugsInPy定范围评测：使用参考补丁选择代码窗口，Agent未看到补丁、测试、标签或另一版本。
- completed仅表示所选窗口及复核完成；完整文件审查数为0，不表示全仓库或全文件审查。
- 修复版本可能含其他缺陷；额外发现不自动计为误报。
- evidence模式使用Agent自行生成的测试与隔离执行，契约语义仍由模型核验；官方回归测试不提供给Agent。

## 已复现缺陷（0）

正式缺陷附测试与运行证据；其余候选和静态建议单列，不表示已经证实。

## 待验证候选与静态建议

### [中] 章节结束时间取到下一章时索引越界

- 位置：`youtube_dl/extractor/youtube.py:1696`
- 来源：llm
- 复核：待验证 — 尚未复核；未运行待审代码。
- 问题：循环使用 enumerate(chapters_list, start=1)，next_num 从 1 开始，而 chapters_list 是 0 基列表。当 next_num < len(chapters_list) 时，代码访问 chapters_list[next_num]，实际取到的是当前章节之后第二个章节（偏移了一位），而不是紧邻的下一章。例如 3 个章节时，第 1 章（next_num=1）的 end_time 取 chapters_list[1]（第 2 章）看似正确，但第 2 章（next_num=2）取 chapters_list[2]（第 3 章），第 3 章（next_num=3）因 3<3 为假而使用 duration。真正的问题是：当 next_num 等于 len(chapters_list) 时条件为假，不会越界；但偏移导致第 2 章的结束时间被设为第 3 章的开始时间，跳过了第 2 章自身的结束边界，使第 2 章区间被错误拉长到第 3 章开始。预期 end_time 应为 chapters_list[next_num-1] 的开始时间（即当前章之后的下一章）。
- 触发条件：watch_next_response 中 chapters 列表含 3 个及以上章节，且各章 timeRangeStartMillis 不同。
- 依据：for next_num, chapter in enumerate(chapters_list, start=1): ... end_time = (chapter_time(chapters_list[next_num]) if next_num < len(chapters_list) else duration)。next_num 为 1 基，chapters_list 为 0 基，chapters_list[next_num] 指向当前章的后两章。
- 修复建议：改为 chapter_time(chapters_list[next_num]) 时使用 next_num 作为 0 基索引，即判断 next_num < len(chapters_list) 后取 chapters_list[next_num] 前先确认语义；正确写法是 end_time = chapter_time(chapters_list[next_num]) if next_num < len(chapters_list) else duration 中 next_num 应为 0 基，或改为 chapters_list[next_num] 当 next_num 从 0 开始枚举。
- 验证方式：候选缺陷不成立。enumerate(chapters_list, start=1) 使 next_num 为 1 基，而 chapters_list 为 0 基；对第 i 章（0 基索引 i-1，next_num=i），chapters_list[next_num] 即 chapters_list[i] 正是紧邻的下一章（0 基索引 i）。因此 end_time 取的是下一章开始时间，语义正确，不存在偏移。当 next_num == len(chapters_list)（最后一章）时条件为假，使用 duration，也不会越界。候选描述中“第 2 章取到第 3 章开始”恰恰是正确行为（第 2 章的结束边界就是第 3 章的开始）。没有可定位的契约被违反，无法构造真实失败的复现测试。

```python
1694:             if start_time is None:
1695:                 continue
1696:             end_time = (chapter_time(chapters_list[next_num])
1697:                         if next_num < len(chapters_list) else duration)
1698:             if end_time is None:
1699:                 continue
```

- 复现状态：unsupported
- 证据说明：候选缺陷不成立。enumerate(chapters_list, start=1) 使 next_num 为 1 基，而 chapters_list 为 0 基；对第 i 章（0 基索引 i-1，next_num=i），chapters_list[next_num] 即 chapters_list[i] 正是紧邻的下一章（0 基索引 i）。因此 end_time 取的是下一章开始时间，语义正确，不存在偏移。当 next_num == len(chapters_list)（最后一章）时条件为假，使用 duration，也不会越界。候选描述中“第 2 章取到第 3 章开始”恰恰是正确行为（第 2 章的结束边界就是第 3 章的开始）。没有可定位的契约被违反，无法构造真实失败的复现测试。

[运行证据](evidence/ac59583e0bd1/evidence.json)

### [低] 描述章节 start_time 超过 duration 时直接 break 丢弃后续有效章节

- 位置：`youtube_dl/extractor/youtube.py:1725`
- 来源：llm
- 复核：待验证 — 尚未复核；未运行待审代码。
- 问题：_extract_chapters_from_description 在 start_time > duration 时执行 break 而非 continue。若描述中章节时间点并非严格递增（例如作者把某章时间写错成大于视频时长，后面又出现合法时间点），后续所有合法章节都会被丢弃。预期应跳过该异常条目继续处理，或至少与 JSON 路径的 continue 行为一致。
- 触发条件：description 中章节时间点序列为 [0:10, 99:00, 0:30]，duration 为 60 秒。
- 依据：if start_time > duration: break；而 _extract_chapters_from_json 对无效 start_time 使用 continue。
- 修复建议：将 break 改为 continue，或在确认时间点单调递增契约后保留 break 并加注释说明。
- 验证方式：候选缺陷声称 start_time > duration 时用 break 会丢弃后续合法章节，但仓库中没有任何文档、测试或语言规则约定描述章节时间点必须非单调递增、或异常条目应被跳过而继续处理。_extract_chapters_from_description 的现有实现（break）与 _extract_chapters_from_json 的 continue 属于不同数据源的不同处理策略，代码本身不能证明期望行为。缺少可定位的契约来断言应返回后续章节，因此无法构造有依据的复现测试。

```python
1723:             if start_time is None:
1724:                 continue
1725:             if start_time > duration:
1726:                 break
1727:             end_time = (duration if next_num == len(chapter_lines)
1728:                         else parse_duration(chapter_lines[next_num][1]))
1729:             if end_time is None:
1730:                 continue
1731:             if end_time > duration:
1732:                 end_time = duration
1733:             if start_time > end_time:
1734:                 break
1735:             chapter_title = re.sub(
1736:                 r'<a[^>]+>[^<]+</a>', '', chapter_line).strip(' \t-')
```

- 复现状态：unsupported
- 证据说明：候选缺陷声称 start_time > duration 时用 break 会丢弃后续合法章节，但仓库中没有任何文档、测试或语言规则约定描述章节时间点必须非单调递增、或异常条目应被跳过而继续处理。_extract_chapters_from_description 的现有实现（break）与 _extract_chapters_from_json 的 continue 属于不同数据源的不同处理策略，代码本身不能证明期望行为。缺少可定位的契约来断言应返回后续章节，因此无法构造有依据的复现测试。

[运行证据](evidence/c435bd5ca046/evidence.json)

### [低] start_time > end_time 时 break 丢弃后续章节

- 位置：`youtube_dl/extractor/youtube.py:1733`
- 来源：llm
- 复核：待验证 — 尚未复核；未运行待审代码。
- 问题：当某章 start_time 大于其 end_time（下一章时间点更早，描述中时间乱序）时执行 break，导致后续所有章节被丢弃。预期应跳过该异常章节继续处理后续条目。
- 触发条件：description 章节时间点为 [0:30, 0:10, 0:50]，duration 为 60 秒。
- 依据：if start_time > end_time: break
- 修复建议：改为 continue 以跳过乱序条目，保留后续有效章节。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
1731:             if end_time > duration:
1732:                 end_time = duration
1733:             if start_time > end_time:
1734:                 break
1735:             chapter_title = re.sub(
1736:                 r'<a[^>]+>[^<]+</a>', '', chapter_line).strip(' \t-')
```

- 复现状态：budget_exhausted
- 证据说明：达到复现候选数量预算。

### [低] average_rating 使用 or 导致 0.0 被后续值覆盖

- 位置：`youtube_dl/extractor/youtube.py:2351`
- 来源：llm
- 复核：待验证 — 尚未复核；未运行待审代码。
- 问题：averageRating 为 '0' 时 float_or_none 返回 0.0，属于合法评分（无评分/零分）。但 `0.0 or try_get(...)` 会把 0.0 当作假值，转而使用 video_info 的 avg_rating，若后者缺失则得到 None，丢失了原本有效的 0.0。预期应保留 0.0。
- 触发条件：video_details['averageRating'] = '0'，且 video_info 中无 avg_rating 或 avg_rating 为 None。
- 依据：average_rating = (float_or_none(video_details.get('averageRating')) or try_get(video_info, lambda x: float_or_none(x['avg_rating'][0])))
- 修复建议：改为显式判断 None：先取 float_or_none，若为 None 再回退到 video_info 的值。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
2349:                 'view count', default=None))
2350: 
2351:         average_rating = (
2352:             float_or_none(video_details.get('averageRating'))
2353:             or try_get(video_info, lambda x: float_or_none(x['avg_rating'][0])))
2354: 
2355:         # subtitles
```

- 复现状态：budget_exhausted
- 证据说明：达到复现候选数量预算。

### [低] 时长为 0 时被当作缺失并回退到其他来源

- 位置：`youtube_dl/extractor/youtube.py:2359`
- 来源：llm
- 复核：待验证 — 尚未复核；未运行待审代码。
- 问题：`if not video_duration` 将 0 视为缺失。若 video_info 的 length_seconds 为 '0'（合法零时长，如直播/占位），会继续用 video_details.lengthSeconds，再回退到 meta duration，可能得到错误时长或 None。预期应仅在 None 时回退。
- 触发条件：video_info['length_seconds'][0] = '0'，video_details 无 lengthSeconds，页面 meta duration 为其他值。
- 依据：video_duration = try_get(video_info, lambda x: int_or_none(x['length_seconds'][0]))
if not video_duration:
    video_duration = int_or_none(video_details.get('lengthSeconds'))
if not video_duration:
    video_duration = parse_duration(...)
- 修复建议：使用 `if video_duration is None:` 判断，保留合法的 0。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
2357:         automatic_captions = self.extract_automatic_captions(video_id, video_webpage)
2358: 
2359:         video_duration = try_get(
2360:             video_info, lambda x: int_or_none(x['length_seconds'][0]))
2361:         if not video_duration:
2362:             video_duration = int_or_none(video_details.get('lengthSeconds'))
2363:         if not video_duration:
2364:             video_duration = parse_duration(self._html_search_meta(
2365:                 'duration', video_webpage, 'video duration'))
2366: 
2367:         # annotations
```

- 复现状态：budget_exhausted
- 证据说明：达到复现候选数量预算。

### [中] decrypt_sig 抛出的 ExtractorError 被外层 except 吞掉并仅警告

- 位置：`youtube_dl/extractor/youtube.py:2399`
- 来源：llm
- 复核：待验证 — 尚未复核；未运行待审代码。
- 问题：re.sub 调用 decrypt_sig，其中 _decrypt_signature 在失败时抛 ExtractorError。该异常被同一 try 的 `except (ExtractorError, KeyError)` 捕获，只 report_warning 后继续，导致该 DASH manifest 被静默跳过；若所有 manifest 都失败，最终可能缺少 DASH 格式而无致命错误。预期签名解密失败应作为提取失败上报（或至少区分处理）。
- 触发条件：mpd_url 含 /s/<sig>，player_url 为 None 或签名函数提取失败，_decrypt_signature 抛 ExtractorError。
- 依据：mpd_url = re.sub(r'/s/([a-fA-F0-9\.]+)', decrypt_sig, mpd_url)
...
except (ExtractorError, KeyError) as e:
    self.report_warning('Skipping DASH manifest: %r' % e, video_id)
- 修复建议：将签名解密移出该 try，或在 except 中区分签名解密失败并重新抛出/致命处理。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
2397:                         return '/signature/%s' % dec_s
2398: 
2399:                     mpd_url = re.sub(r'/s/([a-fA-F0-9\.]+)', decrypt_sig, mpd_url)
2400: 
2401:                     for df in self._extract_mpd_formats(
2402:                             mpd_url, video_id, fatal=dash_mpd_fatal,
2403:                             formats_dict=self._formats):
2404:                         if not df.get('filesize'):
2405:                             df['filesize'] = _extract_filesize(df['url'])
2406:                         # Do not overwrite DASH format found in some previous DASH manifest
2407:                         if df['format_id'] not in dash_formats:
2408:                             dash_formats[df['format_id']] = df
2409:                         # Additional DASH manifests may end up in HTTP Error 403 therefore
2410:                         # allow them to fail without bug report message if we already have
2411:                         # some DASH manifest succeeded. This is temporary workaround to reduce
2412:                         # burst of bug reports until we figure out the reason and whether it
2413:                         # can be fixed at all.
2414:                         dash_mpd_fatal = False
```

- 复现状态：budget_exhausted
- 证据说明：达到复现候选数量预算。

### [低] df 缺少 url 键时 KeyError 被吞并跳过整个 manifest

- 位置：`youtube_dl/extractor/youtube.py:2404`
- 来源：llm
- 复核：待验证 — 尚未复核；未运行待审代码。
- 问题：`df['url']` 直接索引，若 _extract_mpd_formats 返回的格式项无 'url'（例如仅有 'fragment_base_url' 或异常数据），会抛 KeyError，被外层 except 捕获，导致该 manifest 已解析出的其他格式全部丢弃。预期应使用 df.get('url') 或跳过单个格式。
- 触发条件：_extract_mpd_formats 返回的某个 df 不含 'url' 键。
- 依据：if not df.get('filesize'):
    df['filesize'] = _extract_filesize(df['url'])
- 修复建议：使用 df.get('url') 并在缺失时跳过该格式，而非让 KeyError 终止整个 manifest 处理。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
2402:                             mpd_url, video_id, fatal=dash_mpd_fatal,
2403:                             formats_dict=self._formats):
2404:                         if not df.get('filesize'):
2405:                             df['filesize'] = _extract_filesize(df['url'])
2406:                         # Do not overwrite DASH format found in some previous DASH manifest
2407:                         if df['format_id'] not in dash_formats:
```

- 复现状态：budget_exhausted
- 证据说明：达到复现候选数量预算。

## 覆盖范围

| 文件 | 静态检查 | 语义审查 | 完成分块 |
|---|---|---|---|
| youtube_dl/extractor/youtube.py | completed | window_completed | 3/3 |

## 失败记录

```json
[]
```

## 驳回的问题（0）


## 跳过文件

{"unsupported_language_or_resource": 74, "sensitive_file": 1, "benchmark_tests_hidden": 31}

逐文件跳过原因、模型调用用量和复核轨迹见 report.json / run.json。
