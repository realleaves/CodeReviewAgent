# GitHub 仓库代码审查报告

- 仓库：https://github.com/psf/requests
- 分支：main
- Commit：`611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60`
- 状态：**partial**；模式：full；模型：deepseek-flash
- 完成语义审查：3/19 个已索引 Python 文件
- 调用：12；耗时：35.833 秒

## 范围与限制

- 仅支持 Python；外部依赖和业务约定可能缺失。
- 审查基于静态诊断与模型代码推断，未执行待审代码或复现测试。
- supported 表示模型复核认为有代码依据，不代表运行证明或无误报保证。
- 覆盖率以所选 scope 内已索引 Python 文件为分母；索引限制及未支持文件另列。
- 按预算分块；import 关联和只读查询提供有限跨文件上下文。

## 候选问题（5）

### [中] 使用 assert 做依赖版本校验，在 -O 优化模式下会被移除

- 位置：`src/requests/__init__.py:66`
- 来源：llm
- 复核：有代码依据 — 第66、76、78行均用 assert 做 urllib3 版本校验，第118行 except 依赖 AssertionError。以 -O 运行时 assert 被剥离，兼容性检查静默失效。代码依据充分，未运行验证。
- 问题：check_compatibility 使用 assert 来校验 urllib3 版本（第66、76、78行）。当 Python 以 -O / -OO 运行或设置 PYTHONOPTIMIZE 时，assert 语句会被完全剥离，导致版本兼容性检查静默失效，不兼容的 urllib3 版本不会被检测到，可能引发难以排查的运行时错误。第118行虽然捕获 AssertionError，但在优化模式下根本不会抛出。
- 触发条件：以 python -O 或 PYTHONOPTIMIZE=1 运行，且安装了不兼容的 urllib3 版本（如 major<1 或 1.x 且 minor<21）。
- 依据：第66行 `assert urllib3_version_list != ["dev"]`；第76行 `assert major >= 1`；第78行 `assert minor >= 21`；第118行 `except (AssertionError, ValueError)` 依赖 assert 抛异常。
- 修复建议：改用显式条件判断并 raise 自定义异常（或直接 warnings.warn），例如 `if major < 1 or (major == 1 and minor < 21): raise ValueError(...)`，避免依赖 assert。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
64: ) -> None:
65:     urllib3_version_list = urllib3_version.split(".")[:3]
66:     assert urllib3_version_list != ["dev"]  # Verify urllib3 isn't installed from git.
67: 
68:     # Sometimes, urllib3 only reports its version as 16.1.
69:     if len(urllib3_version_list) == 2:
70:         urllib3_version_list.append("0")
71: 
72:     # Check urllib3 for compatibility.
73:     major, minor, patch = urllib3_version_list  # noqa: F811
74:     major, minor, patch = int(major), int(minor), int(patch)
75:     # urllib3 >= 1.21.1
76:     assert major >= 1
77:     if major == 1:
78:         assert minor >= 21
79: 
80:     # Check charset_normalizer for compatibility.
```

### [中] chardet/charset_normalizer 版本解析对非三段版本号会抛 ValueError 被静默吞掉

- 位置：`src/requests/__init__.py:85`
- 来源：llm
- 复核：待确认 — 第82-83、87-88行对 split('.')[:3] 后 int() 转换，非数字段或两段版本确会抛 ValueError 并被第118行吞掉。但 chardet/charset_normalizer 实际发布版本号格式需结合具体依赖版本确认，是否真会触发取决于安装的版本字符串，属依赖上下文。
- 问题：第82-83行和第87-88行将版本号 split('.')[:3] 后直接 int() 转换。若版本字符串包含非数字段（如 '5.0.0.dev0'、'4.0.0rc1' 或 '3.0' 只有两段），int() 会抛 ValueError。该异常在第118行被捕获并降级为一条笼统的警告，导致真实的版本不兼容信息被掩盖，且对两段版本号（如 '3.0'）解包为三个变量会抛 ValueError。
- 触发条件：安装的 chardet 或 charset_normalizer 版本号形如 '5.0.0.dev0'、'4.0.0rc1' 或仅两段 '3.0'。
- 依据：第82行 `major, minor, patch = chardet_version.split(".")[:3]`；第83行 `int(major), int(minor), int(patch)`；第87-88行对 charset_normalizer 同样处理；第118行捕获 ValueError。
- 修复建议：使用健壮的版本解析（如 packaging.version.parse 或正则提取数字段），并对解析失败单独给出明确警告，而非与 urllib3 检查混在同一 except 中。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
83:         major, minor, patch = int(major), int(minor), int(patch)
84:         # chardet_version >= 3.0.2, < 8.0.0
85:         assert (3, 0, 2) <= (major, minor, patch) < (8, 0, 0)
86:     elif charset_normalizer_version:
87:         major, minor, patch = charset_normalizer_version.split(".")[:3]
88:         major, minor, patch = int(major), int(minor), int(patch)
89:         # charset_normalizer >= 2.0.0 < 4.0.0
90:         assert (2, 0, 0) <= (major, minor, patch) < (4, 0, 0)
91:     else:
92:         warnings.warn(
```

### [低] warnings.warn 缺少 stacklevel，警告定位到库内部而非调用方

- 位置：`src/requests/__init__.py:92`
- 来源：llm
- 复核：有代码依据 — 第92、108、119行的 warnings.warn 均未传 stacklevel，默认指向库内部而非调用方。代码依据充分，属可改进的质量问题。
- 问题：第92、108、119行的 warnings.warn 均未指定 stacklevel，默认 stacklevel=1，警告会指向 requests/__init__.py 内部而非触发导入的用户代码，用户难以定位来源。ruff B028 已标记此问题。
- 触发条件：导入 requests 时触发任一依赖警告。
- 依据：第92-96行、第108行、第119-124行的 warnings.warn 调用均无 stacklevel 参数；诊断中 B028 规则命中第92、108、119行。
- 修复建议：为这些 warnings.warn 添加 stacklevel=2（或适当值），使警告指向调用方。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
90:         assert (2, 0, 0) <= (major, minor, patch) < (4, 0, 0)
91:     else:
92:         warnings.warn(
93:             "Unable to find acceptable character detection dependency "
94:             "(chardet or charset_normalizer).",
95:             RequestsDependencyWarning,
96:         )
97: 
98: 
```

### [低] B101: Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.

- 位置：`src/requests/__init__.py:85`
- 来源：bandit B101
- 复核：有代码依据 — 第85行确实使用 assert 校验 chardet 版本范围。在 -O/PYTHONOPTIMIZE 下 assert 被剥离，版本检查静默失效。代码依据充分，属有意设计但存在优化模式失效风险。
- 问题：Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- 触发条件：触发条件需结合业务调用确认。
- 依据：bandit B101: Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- 修复建议：根据诊断检查对应代码。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
83:         major, minor, patch = int(major), int(minor), int(patch)
84:         # chardet_version >= 3.0.2, < 8.0.0
85:         assert (3, 0, 2) <= (major, minor, patch) < (8, 0, 0)
86:     elif charset_normalizer_version:
87:         major, minor, patch = charset_normalizer_version.split(".")[:3]
```

### [低] B101: Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.

- 位置：`src/requests/__init__.py:90`
- 来源：bandit B101
- 复核：有代码依据 — 第90行同样使用 assert 校验 charset_normalizer 版本范围，优化模式下会被移除，检查失效。代码依据充分。
- 问题：Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- 触发条件：触发条件需结合业务调用确认。
- 依据：bandit B101: Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
- 修复建议：根据诊断检查对应代码。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
88:         major, minor, patch = int(major), int(minor), int(patch)
89:         # charset_normalizer >= 2.0.0 < 4.0.0
90:         assert (2, 0, 0) <= (major, minor, patch) < (4, 0, 0)
91:     else:
92:         warnings.warn(
```

## 覆盖范围

| 文件 | 静态检查 | 语义审查 | 完成分块 |
|---|---|---|---|
| src/requests/__init__.py | completed | completed | 2/2 |
| src/requests/__version__.py | completed | completed | 1/1 |
| src/requests/_internal_utils.py | completed | completed | 1/1 |

## 失败记录

```json
[]
```

## 驳回的问题（19）

- `src/requests/__init__.py:102` _check_cryptography 版本比较对非数字段直接返回，可能漏报旧版本：第102-104行对非数字段版本直接 return 跳过检查，但该函数仅用于对 cryptography<1.3.4 发出 slowdown 警告，属非关键提示。含非数字后缀的版本（如 dev/rc）通常为新版本，跳过旧版本警告不构成实际漏报，属有意容错设计。
- `src/requests/_internal_utils.py:46` 使用 assert 做类型校验，优化模式下会被移除：该 assert 是内部辅助函数 unicode_is_ascii 的类型前置条件，函数签名已声明 u_string: str，调用方为 requests 内部代码，不面向不可信外部输入。在 -O 模式下断言被剥离后，若传入 bytes，u_string.encode('ascii') 仍会正常执行（bytes 也有 encode 方法），并非如候选所述抛 AttributeError；且该函数仅用于判断 ASCII，不承担安全校验职责。因此不构成实际缺陷，属误报。
- `src/requests/__init__.py:66` B101: Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.：该 assert 位于 check_compatibility 中，用于校验 urllib3 版本；调用处（第112-124行）已用 try/except (AssertionError, ValueError) 捕获并转为 RequestsDependencyWarning。这是有意的依赖兼容性检查设计，非安全缺陷。
- `src/requests/__init__.py:76` B101: Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.：assert major >= 1 是依赖版本兼容性检查的一部分，异常被上层 try/except 捕获并降级为警告，属有意设计，非安全漏洞。
- `src/requests/__init__.py:78` B101: Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.：assert minor >= 21 同为 urllib3 版本兼容性检查，异常被上层捕获转为 RequestsDependencyWarning，属有意设计，非安全漏洞。
- `src/requests/__init__.py:92` B028: No explicit `stacklevel` keyword argument found：B028 建议 warnings.warn 加 stacklevel，但此处是 requests 包导入时对依赖缺失的告警，指向调用者无意义；且这是库的既有设计，非缺陷。
- `src/requests/__init__.py:108` B028: No explicit `stacklevel` keyword argument found：同上：_check_cryptography 在包导入期发出依赖版本告警，stacklevel 对导入期告警无实际价值，属误报。
- `src/requests/__init__.py:119` B028: No explicit `stacklevel` keyword argument found：依赖版本不匹配告警在模块导入时触发，无有意义的调用栈层级可指向，B028 不适用。
- `src/requests/__init__.py:160` F401: `.__version__.__author__` imported but unused; consider removing, adding to `__all__`, or using a redundant alias：requests/__init__.py 有意重导出 __version__ 元数据（__author__ 等）作为公共 API，F401 属误报。
- `src/requests/__init__.py:161` F401: `.__version__.__author_email__` imported but unused; consider removing, adding to `__all__`, or using a redundant alias：同上，__author_email__ 是包公共元数据重导出，非未使用导入。
- `src/requests/__init__.py:162` F401: `.__version__.__build__` imported but unused; consider removing, adding to `__all__`, or using a redundant alias：同上，__build__ 为包公共元数据重导出，F401 误报。
- `src/requests/__init__.py:163` F401: `.__version__.__cake__` imported but unused; consider removing, adding to `__all__`, or using a redundant alias：同上，__cake__ 为包公共元数据重导出，F401 误报。
- `src/requests/__init__.py:164` F401: `.__version__.__copyright__` imported but unused; consider removing, adding to `__all__`, or using a redundant alias：同上，__copyright__ 为包公共元数据重导出，F401 误报。
- `src/requests/__init__.py:165` F401: `.__version__.__description__` imported but unused; consider removing, adding to `__all__`, or using a redundant alias：该导入位于 src/requests/__init__.py 的 from .__version__ import (...) 块中，是 requests 包对外暴露的公共元数据（__description__ 等），属于有意的 API 设计，并非未使用导入。ruff F401 在此为误报。
- `src/requests/__init__.py:166` F401: `.__version__.__license__` imported but unused; consider removing, adding to `__all__`, or using a redundant alias：同上，__license__ 是 requests 包有意重导出的公共元数据，供用户通过 requests.__license__ 访问，属于设计行为而非未使用导入。
- `src/requests/__init__.py:167` F401: `.__version__.__title__` imported but unused; consider removing, adding to `__all__`, or using a redundant alias：同上，__title__ 为包公共元数据的有意重导出，非未使用导入。
- `src/requests/__init__.py:168` F401: `.__version__.__url__` imported but unused; consider removing, adding to `__all__`, or using a redundant alias：同上，__url__ 为包公共元数据的有意重导出，非未使用导入。
- `src/requests/__init__.py:169` F401: `.__version__.__version__` imported but unused; consider removing, adding to `__all__`, or using a redundant alias：同上，__version__ 是 requests 包最核心的公共属性，被广泛使用，属有意重导出，F401 为误报。
- `src/requests/_internal_utils.py:46` B101: Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.：Bandit B101 仅报告 assert 的存在，属通用风格告警。此处 assert 是内部工具函数的类型前置条件，函数签名已标注 u_string: str，且该函数为 requests 内部使用，不构成安全漏洞。无证据表明可被外部输入触发导致安全影响，属误报/低价值告警。

## 跳过文件

{"outside_scope": 101, "unsupported_language_or_resource": 1, "sensitive_file": 7, "file_count_limit": 16}

逐文件跳过原因、模型调用用量和复核轨迹见 report.json / run.json。
