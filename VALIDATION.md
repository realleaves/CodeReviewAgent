# 验证记录

## 预期依据准入与发现阶段汇总（2026-10-18）

证据模式新增结构化预期准入。`ContractReference`增加`expected_outcome`、`expected_exception`、`precondition`、`assumptions`；新计划必须通过`validate_requirement`。两次执行触达目标后先运行确定性`requirement_gate`：语言规则只能解释实际异常，不能据此要求另一种异常，也不能单独证明返回值/状态/输出；`error_message`不计行为缺陷。模型审计新增`input_supported`、`requirement_supported`、`failure_matches_candidate`、`requirement_class`、`unresolved_assumptions`，`audit_gate`逐项复核，失败或缺失时保持`pending_evidence`。所有检查写入`reproduction.admission`。

离线固定对照使用2026-10-15复测的13条历史自动接受记录，原计划、日志和判读冻结；按每条计划自身文本固定标注预期类型后运行确定性门控。13条中仅PySnooper-3进入审计，12条降级为待确认：1条仅错误消息文案、7条语言规则要求实际未发生的另一种异常、4条语言规则证明返回值/状态/输出。没有把12条判成误报，原证据保留；0次模型API调用、0次Docker执行。脚本`evaluation/expectation_controls.py`会断言只放行`9261f543fc85`并保持13条总数。

项目测试107项通过（本轮新增结构化准入、审计不一致、旧格式接受和13条固定对照等检查），Ruff F/E9及改动文件格式检查通过。旧`replay_evidence`仍只校验原结构，不因旧计划缺少新字段拒绝复跑；历史1/26得分、评分器、参考rubric和72次原始报告均未修改。该结果只验证固定历史记录上的准入行为，尚未测量新提示下的模型产出、新样本检出或误接受变化。详见[实现与固定对照](demo/expectation-admission-20261018/README.md)。

同轮汇总2026-10-15至10-18的三轮发现阶段实验：r0上下文、r1 thinking、r2输出上限，共365次真实provider尝试，三轮参考缺陷命中均为0，默认保持legacy与thinking disabled；因无可核验增益，未按协议启动新样本验证。r2最后一个窗口因进程中断保留为失败，未重试或伪造响应。详见[三轮对照](demo/discovery-context-20261015/README.md)。

## 上下文检索实现与离线检查（2026-10-15）

新增显式`context_strategy=callgraph`实验入口，CLI、正式pipeline和BugsInPy入口已接通，默认legacy。保守静态绑定解析调用方、被调用定义及相关导入；检索已有文档内的相关片段。所有片段有源文件行号，补充内容包含JSON元数据最多10000字符，不追加主片段已覆盖行；未知动态调用不按短名猜测。

修改前冻结当时工作区13个文件和6个已漏检样本清单，两版本18组初始输入构造完毕，共36份输入。旧策略与冻结旧代码真实构造的payload、系统审查提示词一致，主代码保持一致；新片段源码逐字核查和预算检查通过。12个窗口含静态调用方片段，属于检索覆盖，不是模型检出。补充总字符由48057到97519，未来比较需报告真实tokens成本。

全项目86项测试通过（本轮新增21项），Ruff F/E9与CLI帮助检查通过。覆盖别名、重名、局部遮蔽、循环导入、显式方法/模块属性重绑、嵌套函数优先级、文档检索、预算与源码不执行等。0次模型API调用，没有新Docker复现或模型发现/取证成绩，原评分与历史报告不变。详见[完整说明与输入归档](demo/context-callgraph-20261015/README.md)，离线归档校验入口为`python demo/context-callgraph-20261015/verify.py`。

## 历史证据完整复测（2026-10-15）

冻结当前实现和13条历史已接受记录的原测试、输入、镜像ID及快照，旧/新实现各执行两次，共52次；相反参考版本13次；评测者另编的合法格式过滤调用链诊断2次。共67次新容器执行、0次模型API调用。执行时与结束时实现哈希一致，本轮未修改生产代码及已有评分器。

旧执行判定13/13接受，新判定12/13接受，两轮及异常结果一致。新判定拒绝youtube-dl-12错误输入的证据，PySnooper-3有效参考复现保留且修复版通过。12条接受中：1条参考证据成立、6条源码一致性或调用链支持但需维护者确认（含重复记录）、3条待定、1条预期无依据、1条仅异常文案质量。语义判读由Codex完成，未独立人工确认，不将接受数当作真实缺陷数或精确率。

参考修复版仍失败不自动否定额外问题；空格式列表可由合法过滤从非空输入产生，额外诊断在两个版本均确认IndexError，评测者测试不计Agent新命中。没有重跑发现阶段、测量召回或修改历史1/26参考得分。一次反馈继续默认关闭。详见[复测报告与原始归档](demo/evidence-retest13-20261015/README.md)，离线校验入口为`python demo/evidence-retest13-20261015/verify.py`。

验证日期：2026-10-11。环境：Python 3.13.5、Git 2.34.1；依赖完整版本见 requirements.txt。使用工作区现有 deepseek-flash API 配置完成实际调用，凭据未写入源码或报告。

## 功能与依赖

- `python -m pytest -q tests`：25 passed。包含真实 Ruff/Bandit 调用、路径与行号校验、工具轮数收尾、同位置诊断去重、模型预算/输出截断、失败熔断和报告转义。
- `python -m ruff check --isolated --select F,E9 main.py src tests evaluation`：通过。
- `python -m pip check`：无依赖冲突。
- HelloAgents 0.2.9 有一条上游 Pydantic Config 弃用警告，不影响本次运行；没有修改第三方源码。

## 真实 GitHub 仓库

仓库： https://github.com/psf/requests

commit：611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60。

实际命令：

```bash
python main.py review https://github.com/psf/requests \
  --scope src/requests --max-files 3 --max-calls 20
```

完成 __init__.py、__version__.py、_internal_utils.py 三个文件的全部分块，执行12次模型调用，分析耗时35.833秒（不含仓库获取）。19个已索引Python文件中完成3个，覆盖15.8%，按范围限制标为partial；失败记录为空。

保留5个候选项：4个被模型复核为有代码依据、1个待确认；驳回19个候选项。该结果是静态诊断和模型判断，未执行 requests 程序或运行复现。保留项需要维护者结合项目设计继续判断，不能当成5个已确认漏洞。

另对 src/requests/api.py 完成单文件范围的实际审查，状态completed，未保留候选项。结论仅适用于该文件范围。

## 已知缺陷与正常代码

examples/buggy_code.py 的三个已知问题均被检出并复核：

- 第6行：允许空输入的 average 会除零。
- 第9行：默认列表导致 collect 跨调用共享状态。
- 第17行：不可信 username 直接拼接到 SQL。

examples/clean_code.py 无保留问题。静态规则与模型发现合并后共3项，工具证据仍可在JSON追溯。实际模型调用3次，运行耗时21.197秒。为验证去重，最终报告使用既有实际候选和复核结果执行新版后处理；原始调用与复核轨迹保留。

## 三种方式对比

最终版本运行 evaluation/cases.json 前4个样本：2个缺陷、2个正常。三种模式均完成4/4样本。

| 模式 | 命中已知缺陷 | 额外bug候选 | 调用 | 耗时 |
|---|---:|---:|---:|---:|
| direct | 2 | 1 | 4 | 5.772s |
| assisted | 2 | 0 | 4 | 5.713s |
| full | 2 | 0 | 6 | 7.484s |

direct 的额外候选认为正常 average 的空输入返回 int 0、非空返回 float 是bug；样本约定没有要求统一float返回类型，因此该候选缺少必要契约依据。自动评分仅按位置与类别粗匹配；这组数据是冒烟验证，不足以推断泛化准确率或复核的普遍收益。每个样本报告和原始匹配信息保留在本工作区 outputs/evaluation-final/。

## HTML 报告

浏览器插件没有可用连接，使用本机独立 Firefox headless 配置作验证。桌面1440px和手机390px下，各8项实际DOM检查通过：全部/保留问题、风险和状态筛选、无匹配搜索、空结果提示、文件搜索、视口横向溢出。截图已目视检查。验收脚本中的PASS横条只出现在验收截图，正式报告不包含此横条。

原始检查结果和截图见 demo/browser-qa/。没有在用户已有浏览器配置中登录或读取会话。

## BugsInPy 真实缺陷验证（2026-10-11）

固定官方数据 commit `11c5f1eea954a42132cfd06bf257766a7963e0fd`，预选 PySnooper 1–3、tornado 1–8、youtube-dl 1–9。使用现有 `deepseek-flash` 配置，20个缺陷×2版本×2模式共80次审查，79次完整完成，257次真实模型调用。

19/20个缺陷在隔离容器中实现指定测试的缺陷版失败、修复版通过。PySnooper-2 因重建快照依赖不一致排除；PySnooper-1/direct 因修复版模型 JSON 无效排除。补齐 PySnooper 历史依赖后的测试复跑保留初次日志，并未再次调用模型或修改目标代码。

对照参考补丁、测试和解释的模型辅助判读：direct 检出4/18个有效缺陷（22.2%），full 检出3/19个（15.8%）；共同有效的18对上分别为4和3。限定已知位置窗口，不代表全仓库检测能力；语义判读仍需人类复查。详细依据、80份原始 JSON、复现日志和排除理由见 [demo/bugsinpy/README.md](demo/bugsinpy/README.md)。

新增评测协议、固定清单、可重复准备/审查/隔离复现/只复跑测试/显式语义评分入口。格式纠正使用额外实际模型调用并计入预算，仍不能保证服务商总返回有效 JSON。单元和集成检查覆盖补丁解析、快照重建、数据泄漏排除、窗口预算、JSON纠正、测试命令限制及评分证据约束。

项目 pytest 的收集范围固定为 `tests/`，避免下载的历史仓库测试混入当前 Python 环境；历史缺陷复现由 Docker 入口单独执行。此前默认全目录收集导致1140项历史测试收集错误，该次未运行测试，不能作为项目测试结果。

最终项目检查：`pytest -q` 为42项通过，只有 HelloAgents 上游 Pydantic 弃用警告；Ruff F/E9检查通过，新增评测文件格式检查通过。80份上传的 JSON 报告与本地原报告哈希一致，文档链接与报告路径已核对。

## 复现证据首版检查点（2026-10-13）

CLI默认 evidence，新增行为审查、最小 unittest 生成、契约引用检查、两次隔离执行、模型契约核验和保存证据复跑。仅 reproduced 进入正式缺陷计数；静态建议和未证实候选单列。保留旧推断模式作对照。

当前代码实际运行 `main.py review examples/evidence --local --max-files 2 --max-calls 16`，使用已有 deepseek-flash 配置，4次模型调用，状态 completed。按文档承诺空输入返回0.0的平均值实现，在两个全新容器中都产生 ZeroDivisionError；正常实现无候选。实际镜像中的 Python为3.13.16，镜像 ID和日志见 [实际报告](demo/evidence-checkpoint/report.md)。从上传证据运行 reproduce 命令再次观察到同一失败，0次模型调用。

54项项目测试通过，Ruff F/E9检查通过，只有原有上游 Pydantic 弃用警告。新增检查涵盖伪造契约、无条件失败、无关失败、导入错误、测试通过、两次执行、核验预算不足、一次纠正及源码哈希变化。

真实缺陷首轮试跑已完成3个缺陷对共6次审查，暴露导入白名单和输出格式限制，结果留在本地 outputs/evidence-real-pilot。8个新固定样本初次试跑在修正入口时中止；完整复跑与参考问题判读未完成。这个提交是用户要求先上传的实现检查点，不能声称新版真实缺陷检出率已经提升，也未完成新版HTML浏览器交互回归。

## 复现证据版实际测评（2026-10-14）

上述“完整复跑未完成”是2026-10-13检查点状态；本次冻结commit `40034c2`完成原20对的40次evidence审查、新8对的32次direct/evidence审查。两批11个src文件的SHA256与运行前记录完全一致，未修改源码、提示词、预算或已有评分器。使用现有DeepSeek配置，共434次模型调用，69/72个所选窗口完整，35/72条完整流程completed。

官方测试成对复现27/28个计划缺陷。证据版有效18+8=26对，候选识别4/26、匹配参考问题的有效生成证据1/26（3.8%）；新8对有效生成证据0/8。官方测试失败或窗口不完整的对显式排除，候选的unsupported、invalid_plan、复现失败和证据预算不足继续计为未命中。结果是已知位置窗口的Codex模型辅助判读，等待人工复查，不作为全仓库准确率。

唯一有效参考命中为PySnooper-3的undefined output_path；原生成测试两次NameError，另一次未改测试的独立对照在缺陷版失败、修复版通过。youtube-dl-12生成测试使用错误语法`!ext=mp4`，独立放到修复版仍发生相同断言失败，已否定Agent的reproduced标签；评测侧改为`ext!=mp4`后，缺陷版失败、修复版通过，人工纠正不计Agent命中。103个证据候选有13个被Agent自动接受，其他额外问题尚未全部判真伪，不能用1/13作为全局精确率。

72次原始报告、生成测试、官方测试、独立对照共634个文件已归档，ZIP解压校验与逐文件SHA256一致。结构化分数、逐次候选ID与判读理由、冻结配置和浏览器总览见[实际测评资料](demo/evidence-assessment-20261014/README.md)。本轮只新增测评资料与文档；前一检查点的54项项目测试结果仍归属于那个代码版本。

## Primuus参考机制首轮实施（2026-10-15）

先保存40034c2的源码基线、13条旧证据判定和实验协议，再修改执行位置判定、可信异常帧及一次有界反馈。新判定不再把同函数调用当作目标位置触达，测试执行的追踪与导入阶段分离。旧13条自动接受记录重判仅拒绝已知错误的youtube-dl-12；其余12条真实性仍未全部判读。用新容器执行PySnooper-3和youtube-dl-12的缺陷/修复对照，分别得到有效异常/通过和两侧均拒绝；两个通用Docker反例也均拒绝，0次模型调用。

固定tornado-4原候选、源码和首次生成计划，两条件共用新判定，只切换一次反馈，按运行前固定顺序完成3组成对实验。新增5次现有DeepSeek调用（上限24），两条件有效证据均0/3；开启反馈分别因结构不合规、初始化失败、继续复制逻辑未触达目标而结束。根据预定否决条件，max_repro_repairs保持默认0。没有修改既有评分、原始72次报告或扩大采样。

65项项目测试通过，Ruff F/E9及改动文件格式检查通过，CLI参数入口通过。原始诊断报告曾沿用旧窗口报告的范围/选项/计数；已离线生成修正的展示副本，候选、调用、测试、执行与判定不变，原始报告和执行时驱动按哈希保留。源码哈希确认采样期间核心实现未变。实验协议、全部原始诊断、展示修正来源及结果见[首轮对照资料](demo/primuus-controls-20261015/README.md)。本轮不提供新的全仓库或盲测检出率结论。


## 发现对照与新样本验证最终交付（2026-10-21）

legacy/callgraph与两轮单变量改进均结束，另完成预选4新样本、44窗口对照。全目标260计划窗口，436/600次保守扣减，含失败和响应不明的0365；不追加调参或模型请求。开发6样本未见参考增益。新样本关闭思考22/22窗口完整，两次区分2/4、1/4；开启11/22完整，每次仅1对可评分，共同对两组均识别，不能解释为100%更优。

额外Host大小写问题由评测者3容器对照支持，未计入参考命中或Agent生成证据；原1/26成绩不变。新4样本官方双版本均复现，8个容器；另保留2个r0额外候选反证。新样本42窗口后退出，只续跑2个未启动窗口，已有失败不重试。

当前项目107项测试通过，Ruff F/E9通过。完整逐组判读（待人工复查）、冻结配置、原始请求/错误、运行日志与标准库独立校验见[最终资料](demo/discovery-context-20261015/README.md)。预期准入生产改动与发现实验成绩分开陈述。没有GitHub推送。

## 准入固定案例验证（2026-10-21）

用4个已见固定候选做真实模型对照：PySnooper-3文档正例、tornado-1 fixed、youtube-dl-4 fixed、youtube-dl-8 buggy。模型重新生成计划，两次隔离Docker后先过确定性`requirement_gate`，通过后再做结构化审计。最终干净运行5次provider调用、4次容器执行：PySnooper-3两次NameError触达目标，requirement与audit 6项检查全部通过，保持`reproduced`；tornado-1 fixed和youtube-dl-4 fixed由模型直接返回`applicable=false`，状态`unsupported`，未执行容器；youtube-dl-8 buggy实际两次AttributeError，但计划要求SyntaxError，确定性门控拒绝为`contract_unconfirmed`，未花审计调用。

本轮同时发现当前沙箱的Docker daemon看不到`/tmp` bind mount，前两次诊断运行因此出现`environment_failed`；把`TMPDIR`指到工作区内后挂载正常。三轮诊断尝试合计12次请求，均有记录；最终干净运行5次。该验证只证明固定正反例行为，不是新样本检出率或全局精确率；历史旧判定（4个都曾reproduced）只作参考，不是重新采样的成对基线。youtube-dl-8的底层AttributeError看起来真实，但SyntaxError预期无文档/测试依据，降级是保守取舍，可能误杀真实问题。

离线校验：`python demo/admission-validation-20261021/verify.py`，核对4个案例、5次请求/响应配对、预算、正负例状态、审计字段、附件哈希与源码冻结哈希，不调用模型或Docker。资料见[固定案例验证](demo/admission-validation-20261021/README.md)。

## 新样本 evidence 对照（2026-10-21）

在4个预选holdout样本（tornado-13、youtube-dl-14、tornado-14、youtube-dl-15）上做第一次evidence-stage对照：每样本缺陷/修复两侧，baseline（`enforce_admission=False`）与admission（`True`）两臂；同一提示词、模型、生产代码窗口、单次8次调用上限和最多2个复现候选。共16次运行、37次provider调用（baseline 18、admission 19），两臂完整窗口均8/8，无provider错误；全局上限140，实际37。官方测试4/4成对复现，测试/补丁/标签只在评测侧。

结果：两臂都是参考缺陷有效检出1/4、修复侧同问题告警0、成对区分1/4；唯一有效命中是tornado-14的`initialize(make_current=True)`条件取反，两臂都两次隔离执行并审计通过。tornado-13只有Ruff B904静态建议，无模型候选；youtube-dl-14候选偏离网页JSON章节元数据参考路径；youtube-dl-15无候选。admission相对baseline多1次调用、多5条待确认候选（13 vs 8），没有增加有效证据，也没有破坏唯一正例。判读为DeepSeek对照冻结reference-rubric，人工复查待完成；额外候选不自动算误报。

该对照只隔离门控（两臂共享新提示词），不是旧版vs新版；样本复用discovery holdout，单次重复，不是完全盲测或全仓库成绩。结论：准入在固定案例上拦住了无依据预期，但在这个小样本evidence pilot上没有显示端到端检出/精确率收益；不能据此声称提升，也不足以关闭安全门控。资料见[新样本evidence对照](demo/evidence-holdout-compare-20261021/README.md)；离线校验`python demo/evidence-holdout-compare-20261021/verify.py`，不调用模型/Docker。当前项目111项测试通过，Ruff F/E9通过。

## 漏检失败分类（2026-10-21）

对2026-10-14冻结测评的26个有效参考对做逐条候选阶段分类，0次模型调用、0次Docker。候选命中4个、有效证据1个；22个漏检中8个完全没有候选（buggy侧无任何LLM finding，运行多为completed且1–2次调用）、14个有候选但偏题（其中4个复现了额外问题）、另3个候选命中但证据失败。分类脚本`evaluation/evidence_failure_taxonomy.py`会断言26/4/1/22以及8/14/3分组；结构化结果与逐条参考问题见[失败分类](demo/evidence-failure-taxonomy-20261021/README.md)。

结论：瓶颈在发现阶段，不在取证/准入门控。8个无候选说明当前单次广撒网提示允许模型看一眼就返回空；14个偏题集中在输入变体、状态/生命周期、协议/头部和regex/编码。下一轮按长期目标做“假设—反例式发现流程”的单变量A/B，先写协议和预算，再启动模型调用；不继续加callgraph/thinking/输出上限或收紧准入。当前109项测试通过，Ruff F/E9通过。

## P1 假设—反例式发现（2026-10-21，已运行，未采用）

实现`review_strategy=hypothesis`实验提示：要求模型先输出契约/前置条件/不变量理解、3–5个行为假设、每个假设的最小反例和契约来源、实际核对过的调用方/定义/文档/测试，再输出最多4条有具体反例的候选；零候选时仍须用`checked`/`hypotheses`说明检查过什么。结构化schema为`checked`/`hypotheses`/`findings`，`findings`仍走原有行号校验和去重。默认`review_strategy=baseline`；CLI新增`--review-strategy`，pipeline和BugsInPy入口已接通。

P1协议冻结6个开发样本（tornado-1/3/7、youtube-dl-2/4/8）、两侧、18个r0输入窗口、baseline/hypothesis两臂、1次重复、80次调用上限、每窗口最多3次；两臂只改`review_strategy`，模型/上下文/thinking/输出上限相同。只跑发现阶段，不启动证据引擎；官方测试/标签/相反版本不进入Agent输入。setup校验12个snapshot、18个窗口，预算0/80，provider配置为deepseek-flash/disabled/0.1/6000。

实际运行36/36窗口完成、39/80次调用；baseline候选命中1/6（youtube-dl-4无参调用regex），hypothesis 0/6；两臂修复侧同参考问题告警均为0。hypothesis候选更多（33 vs 29），但**工具读取为0**（baseline 6），`checked`声称的核对没有对应工具调用；completion tokens从8,187升到19,165。未达到采用条件，默认保持baseline。机制结论：只在提示词里要求核对、用自由文本自报`checked`不够，下一轮P1b必须让`checked`引用真实工具读取并由代码校验。

结果与离线校验见[demo/discovery-hypothesis-20261021](demo/discovery-hypothesis-20261021/README.md)；`python demo/discovery-hypothesis-20261021/verify.py`核对36窗口、39请求/响应、24条判读、评分重算和源码冻结哈希。当前115项测试通过，Ruff F/E9通过。

## P1b 工具证据强制 smoke（2026-10-21）

P1 的 hypothesis 臂 0 次真实工具读取，`checked` 是自报。P1b 新增 `review_strategy=hypothesis_tools`：首轮没有真实工具读取时执行一次有界重试；重试后仍无读取则丢弃 findings，trace记录`tool_evidence=false`/`findings_dropped=no_tool_evidence`。样本为 tornado-3、youtube-dl-4、youtube-dl-8两侧各1窗口，共6窗口/臂；P1账本39/80，P1b phase上限41，实际19，总58/80。

结果：baseline 0/3、hypothesis_tools 0/3，修复侧告警均0；baseline完成6/6、工具读取2、调用7、候选16；hypothesis_tools完成4/6、失败2、工具读取4、重试4、丢弃findings2、调用12、候选3。工具强制确实增加了读取（tornado-3 buggy、youtube-dl-8 fixed），但在关键youtube-dl-4 buggy窗口重试后仍无工具调用，findings被丢弃；P1b的baseline也未复现P1的youtube-dl-4命中（生成的是`f( )`空白参数候选而非`f()` regex），说明单次采样波动明显。两个失败窗口是`expected_behavior`最短10字符的schema过严；该限制已放宽到1，避免未来无意义失败。

决定：P1b当前实现不采用。不是“工具读取没增加”，而是强制后仍无法让模型在关键窗口真正读工具，严格丢弃findings反而降低召回。下一轮若继续工具证据方向，需要tool-first流程或原生tool calling，而不是再加一次同样的文字重试。P1b资料见[demo/discovery-hypothesis-20261021](demo/discovery-hypothesis-20261021/README.md)，离线校验`python demo/discovery-hypothesis-20261021/verify-p1b.py`；当前119项测试通过，Ruff F/E9通过。
