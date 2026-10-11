# GitHub 仓库代码审查报告

- 仓库：local
- 分支：working-tree
- Commit：`local-unversioned`
- 状态：**completed**；模式：full；模型：deepseek-flash
- 完成语义审查：2/2 个已索引 Python 文件
- 调用：3；耗时：21.197 秒

## 范围与限制

- 仅支持 Python；外部依赖和业务约定可能缺失。
- 审查基于静态诊断与模型代码推断，未执行待审代码或复现测试。
- supported 表示模型复核认为有代码依据，不代表运行证明或无误报保证。
- 覆盖率以所选 scope 内已索引 Python 文件为分母；索引限制及未支持文件另列。
- 按预算分块；import 关联和只读查询提供有限跨文件上下文。

## 候选问题（3）

### [高] average 对空列表触发 ZeroDivisionError

- 位置：`buggy_code.py:6`
- 来源：llm
- 复核：有代码依据 — 第5行文档声明空输入应返回 0，第6行直接 sum(values)/len(values)，空列表时 len 为 0 会抛 ZeroDivisionError，与声明契约不符，且无空值保护。
- 问题：文档字符串明确说明空输入应返回 0，但实现直接执行 sum(values)/len(values)。当 values 为空时 len(values) 为 0，会抛出 ZeroDivisionError，与声明的契约不符。
- 触发条件：调用 average([]) 或传入任何空可迭代对象（如 average(())）。
- 依据：第 5 行文档："empty input should return zero"；第 6 行：return sum(values) / len(values)，未对空输入做判断。
- 修复建议：在除法前判断空输入，例如：if not values: return 0，然后再返回 sum(values)/len(values)。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
4: def average(values):
5:     """Accept a possibly empty numeric list; empty input should return zero."""
6:     return sum(values) / len(values)
7: 
8: 
```

### [高] collect 使用可变默认参数导致跨调用状态泄漏

- 位置：`buggy_code.py:9`
- 来源：llm + ruff B006
- 复核：有代码依据 — 第9行 items=[] 在函数定义时仅创建一次，第11行 append 修改共享列表，未传 items 的多次调用会累积状态，与第10行文档“每次调用获得独立新列表”矛盾。
- 问题：items=[] 作为默认参数在函数定义时只创建一次，所有未显式传入 items 的调用共享同一个列表。文档字符串要求每次调用获得独立的新列表，但实际会不断累积之前的值，造成隐蔽的状态污染。
- 触发条件：连续调用 collect(1) 后再调用 collect(2)，第二次返回 [1, 2] 而非 [2]。
- 依据：第 9 行 def collect(value, items=[]): 使用可变默认值；第 11 行 items.append(value) 直接修改该共享对象。
- 修复建议：将默认值改为 None 并在函数体内创建新列表：def collect(value, items=None): if items is None: items = []。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
7: 
8: 
9: def collect(value, items=[]):
10:     """Each call without items should get its own fresh list."""
11:     items.append(value)
12:     return items
13: 
14: 
```

### [高] lookup 通过 f-string 拼接 SQL 造成注入

- 位置：`buggy_code.py:17`
- 来源：llm + bandit B608
- 复核：有代码依据 — 第16行注释说明 username 来自不可信 HTTP 客户端，第17行用 f-string 拼接进 SQL，攻击者可通过引号闭合改变查询语义，构成 SQL 注入。
- 问题：username 来自不可信 HTTP 客户端，却被直接插入 SQL 字符串。攻击者可构造如 ' OR '1'='1 的输入改变查询语义，或利用引号闭合执行任意 SQL，导致数据泄露或篡改。
- 触发条件：调用 lookup(conn, "' OR '1'='1") 或传入包含单引号与 SQL 片段的用户名。
- 依据：第 16 行注释："username is supplied by an untrusted HTTP client"；第 17 行使用 f"SELECT * FROM users WHERE name = '{username}'" 直接拼接。
- 修复建议：使用参数化查询，例如 connection.execute("SELECT * FROM users WHERE name = ?", (username,))，避免字符串拼接。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
15: def lookup(connection, username):
16:     """username is supplied by an untrusted HTTP client."""
17:     return connection.execute(f"SELECT * FROM users WHERE name = '{username}'").fetchall()
```

## 覆盖范围

| 文件 | 静态检查 | 语义审查 | 完成分块 |
|---|---|---|---|
| buggy_code.py | completed | completed | 1/1 |
| clean_code.py | completed | completed | 1/1 |

## 失败记录

```json
[]
```

## 驳回的问题（0）


## 跳过文件

{}

逐文件跳过原因、模型调用用量和复核轨迹见 report.json / run.json。
