# 14 设置字段速查（界面帮助汇总）

设置页字段旁的帮助文案汇总如下，改配置时可先查「是什么、怎么用」。

内容来自产品内嵌帮助（`settingsHelp`），与线上设置页保持一致；若界面已改文案，**以屏幕为准**。

> 💡 第一次配置请仍按 [10 设置](10-settings.md) 的「先模型、再自选、再通知」走。本章是查字典，不是从零教程。

> ⚠️ 改配置请先**保存**再测试。密钥不要截图外传。

## 基础 / 自选与通用

| 字段（界面标题） | 一句话说明 | 怎么用（摘要） |
| --- | --- | --- |
| **自选股列表** | 配置需要分析的股票代码列表，是手动分析、定时任务和通知报告的基础输入。 | 多个股票代码推荐使用英文逗号分隔；从表格或聊天中粘贴时，也会识别中文逗号、顿号、分号、空格和换行，并在保存后规范为英文逗号。 |

## AI 与模型

| 字段（界面标题） | 一句话说明 | 怎么用（摘要） |
| --- | --- | --- |
| **分析生成方式** | 决定系统用哪种方式生成个股分析、大盘复盘和普通文本回复。 | 通常保持“默认模型配置”。只有在本机已安装并登录对应 CLI，且你信任它处理分析内容时，才选择本地 CLI 生成方式（实验）。 |
| **备用生成方式** | 决定本地 CLI 生成失败后，是直接报错，还是再尝试默认模型配置。 | 选择“禁用”表示失败就报错；选择“默认模型配置”表示再尝试你已经配置好的普通模型。 |
| **OpenCode CLI 模型** | 可选：指定 StockPulse 调用 OpenCode run 时传给 --model 的模型名。 | 仅在“分析生成方式”选择 OpenCode CLI 时生效。留空时 StockPulse 不传 --model，使用你本机 OpenCode 的默认模型配置。 |
| **生成超时（秒）** | 限制一次模型生成最多等待多久。 | 默认 300 秒，主要用于本地 CLI 这类命令行生成方式。 |
| **最大输出大小（字节）** | 限制一次本地命令行生成可读取的输出大小。 | 默认 1048576 字节。超过限制时会停止解析，并记录“输出过大”错误。 |
| **模型生成最大并发** | 限制同时进行的模型生成任务数量。 | 默认 1。使用本地 CLI 生成方式时，实际并发还会受“本地命令行最大并发”限制。 |
| **本地命令行最大并发** | 限制同时启动多少个本地命令行生成进程。 | 默认 1，避免同时启动多个本地 CLI 进程导致机器变慢或输出互相干扰。 |
| **主要模型** | 指定普通分析流程默认使用的模型。 | 从可用模型中选择；留空时系统会根据已配置的模型连接自动选择。 |
| **LLM 连接列表** | 声明多个模型连接，用于多 provider、多 Key、备用模型和可视化连接管理。 | 填写逗号分隔的连接名，例如 deepseek,aihubmix；每个连接再配置 LLM_<NAME>_BASE_URL、LLM_<NAME>_API_KEY(S)、LLM_<NAME>_MODE… |
| **Agent 主要模型** | 为问股、策略 Agent 等 Agent 场景单独指定模型。 | 从可用模型中选择；留空时继承普通分析的主要模型。 |
| **Vision 模型** | 为图片理解任务选择模型。 | 从可用模型中选择；留空时使用系统默认策略。 |
| **备用模型** | 主要模型失败时按顺序尝试的备用模型列表。 | 从可用模型中选择一个或多个，按顺序尝试。 |
| **高级模型路由 YAML** | 指定 LiteLLM 原生 YAML 路由文件，适合复杂路由、限流和专家配置。 | 填写项目可访问的 YAML 文件路径，例如 ./litellm_config.yaml。 |
| **模型配置来源模式** | 选择当前生效的模型配置来源。 | auto 保持历史优先级（YAML > Channels > legacy）；channels/yaml/legacy 只强制单一来源。 |
| **Temperature** | 控制模型输出随机性。 | 取值范围 0.0 到 2.0；越低越稳定，越高越发散。 |
| **Prompt Cache 遥测** | 记录 provider 返回的 prompt cache usage 与归一化诊断。 | 默认开启。关闭后不持久化 provider raw usage JSON、normalized cache fields 和 cache decision diagnostics，基础 toke… |
| **Prompt Cache Hints** | 允许主分析路径主动发送已验证 provider-specific cache hint。 | 默认关闭。开启后仍只会对 registry 中 verified 或 smoke-tested 的 provider/route 发送 prompt_cache_key、cache_contro… |
| **Prompt Cache 诊断级别** | 控制 prompt cache capability 与 hint 决策诊断细节。 | 可选 off、basic 或 debug。非法值会回退为 off。 |
| **LLM 用量 HMAC 密钥** | 用于 LLM usage telemetry 的 message-level HMAC 指纹。 | 通常留空即可，系统会在数据目录生成本地密钥文件；只有需要跨部署比较 HMAC 时才手动配置同一个高熵随机密钥，例如 openssl rand -hex 32。 |
| **LLM 用量 HMAC 版本** | 标记当前 LLM usage HMAC 密钥版本。 | 轮换 LLM_USAGE_HMAC_SECRET 时同步更新，例如 prod-2026-06。 |
| **模型服务 API Key** | 配置模型服务商或聚合网关的访问密钥。 | 在对应服务商控制台创建 API Key 后填入；如需轮换或负载均衡，对应的多 Key 变体字段使用英文逗号分隔。 |
| **Anspire LLM 网关** | 使用 Anspire API Key 作为 OpenAI-compatible 模型网关的兼容入口。 | ANSPIRE_LLM_ENABLED 控制是否启用该兼容路径；ANSPIRE_LLM_BASE_URL 指定网关地址；ANSPIRE_LLM_MODEL 指定未显式选择主要模型时的默认模型。 |
| **Legacy Provider 参数** | 为旧版 provider 专用配置路径设置模型名、温度或 token 上限。 | 这些字段用于兼容历史配置；新配置优先使用 LITELLM_MODEL、LITELLM_FALLBACK_MODELS、VISION_MODEL、LLM_TEMPERATURE 或 LLM Cha… |
| **OpenAI 兼容 Base URL** | 指定 OpenAI-compatible 服务的接口根地址。 | 通常以 /v1 结尾；官方接口、中转网关和本地兼容服务的地址各不相同。 |

## 数据源

| 字段（界面标题） | 一句话说明 | 怎么用（摘要） |
| --- | --- | --- |
| **Tushare Token** | 用于访问 Tushare Pro 数据接口。 | 在 Tushare 账户中获取 token 后填入。 |
| **TickFlow API Key** | 用于启用 TickFlow A 股日 K、实时行情、股票列表/名称与大盘复盘增强数据。 | 在 TickFlow 获取 API Key 后填入；未配置时系统会继续使用其他可用数据源和降级路径。 |
| **TickFlow 日 K 优先级** | 控制 TickFlow 在 A 股日 K 数据源回退链中的位置。 | 填写整数；数字越小越早尝试，默认 2。未配置 TICKFLOW_API_KEY 时该优先级不会生效。 |
| **TickFlow 日 K 复权模式** | 控制 TickFlow 日 K 线的复权口径。 | 可选 none、forward、backward、forward_additive 或 backward_additive。默认 none。 |
| **TickFlow 批量日 K 预取** | 控制批量分析时是否先用 TickFlow 批量接口预热日 K 缓存。 | 默认开启。如果当前套餐没有批量日 K 权限，系统会短期记住失败状态并继续回退。 |
| **TickFlow 批量大小** | 控制 TickFlow 日 K 和实时行情批量请求的单批最大标的数。 | 填写正整数，默认 100。标的数超过该值时系统会拆分多批请求。 |
| **股票索引远程更新** | 从 GitHub main 分支获取最新股票自动补全索引，并缓存到本地。 | 默认开启；如运行环境无法访问 GitHub raw，可关闭开关。远程 URL、检查频率和超时时间均为系统内置值。 |
| **AlphaSift 选股** | 控制是否启用内置 AlphaSift 选股页。 | 默认关闭。设为 true 后，Web 会检查随后端依赖安装的 alphasift.dsa_adapter；若缺失，请在仓库根目录依次运行 python -m pip install --upgr… |
| **AlphaSift 安装来源** | 配置显式修复安装使用的受信任 AlphaSift pip 来源。 | 默认固定到已验证的 ZhuLinsen/alphasift commit；正常部署通过 requirements 安装，只有手动调用修复安装入口时才使用该来源。 |
| **实时行情源优先级** | 配置多个实时行情源的尝试顺序。 | 优先级使用英文逗号分隔；系统会按顺序尝试可用数据源。 |
| **实时行情配置** | 控制实时行情和盘中技术指标是否启用。 | 开关字段使用 true/false；行情源顺序由 REALTIME_SOURCE_PRIORITY 单独配置。 |
| **搜索服务 API Key** | 配置新闻与搜索增强所需的第三方搜索服务密钥。 | 多 Key 字段使用英文逗号分隔；系统会按现有搜索优先级和可用性选择服务。 |
| **SearXNG 实例地址** | 配置自建或可信 SearXNG 搜索实例。 | 多个实例使用英文逗号分隔；自建实例需要启用 JSON 输出格式。 |
| **筹码分布分析** | 控制是否启用筹码分布相关分析。 | 云部署或数据源不稳定时可设为 false。 |
| **乖离率阈值** | 设置股价偏离 MA5 的风险提示阈值。 | 填写百分比数值；当价格偏离 MA5 超过阈值时，报告会提示避免追高或注意回归风险。 |
| **Pytdx 通达信服务器** | 配置通达信行情服务器地址，覆盖内置默认服务器。 | 可分别填写 PYTDX_HOST/PYTDX_PORT，也可使用 PYTDX_SERVERS 填写多个 ip:port；PYTDX_SERVERS 优先级更高。 |
| **新闻时间窗口** | 控制纳入分析上下文的新闻时效范围。 | NEWS_MAX_AGE_DAYS 设最大天数，NEWS_STRATEGY_PROFILE 设窗口策略。 |

## 通知

| 字段（界面标题） | 一句话说明 | 怎么用（摘要） |
| --- | --- | --- |
| **飞书群机器人 Webhook** | 配置飞书自定义群机器人，用于把分析报告推送到指定飞书群。 | 在飞书群中添加自定义机器人后，复制 open-apis/bot/v2/hook 开头的 Webhook URL 到这里。 |
| **飞书 Stream 模式** | 启用飞书应用机器人 / Stream Bot 长连接模式，不是飞书群 Webhook 推送开关。 | 只有在已创建飞书应用、完成应用发布、权限和事件订阅配置后才开启；同时需要 FEISHU_APP_ID 和 FEISHU_APP_SECRET。 |
| **飞书 App Bot 推送目标** | 配置飞书应用机器人主动推送的目标 chat_id（群聊模式）或 open_id（私聊模式）。 | 需要同时填写 FEISHU_APP_ID 和 FEISHU_APP_SECRET。群聊模式填写 oc_ 开头的 chat_id；私聊模式填写 ou_ 开头的 open_id 并将 FEISHU_… |
| **飞书接收方 ID 类型** | 指定 FEISHU_CHAT_ID 的类型：chat_id 表示群聊，open_id 表示私聊。 | 群聊选择 chat_id；私聊（给指定用户发 P2P 消息）选择 open_id。 |
| **飞书 API 域名** | 选择飞书 API 的区域：feishu 对应飞书国内版（feishu.cn），lark 对应 Lark 国际版（larksuite.com）。 | 国内用户选择 feishu；海外 / Lark 用户选择 lark。 |
| **钉钉 Stream 模式** | 启用钉钉应用机器人长连接模式，不是普通钉钉群机器人 Webhook 开关。 | 需要先在钉钉开放平台配置应用机器人，并填写 DINGTALK_APP_KEY 和 DINGTALK_APP_SECRET。 |
| **企业微信 Webhook** | 配置企业微信群机器人 Webhook，用于把分析报告推送到指定群。 | 在企业微信群中创建机器人后，复制 qyapi.weixin.qq.com/cgi-bin/webhook/send 开头的 Webhook URL。 |
| **自定义 Webhook** | 向任意支持 POST JSON 的服务推送报告。 | 多个 URL 使用英文逗号分隔；如需自定义 body，可配置 CUSTOM_WEBHOOK_BODY_TEMPLATE。 |
| **Webhook SSL 校验** | 控制发送 HTTPS Webhook 时是否校验证书。 | 默认保持 true；只有可信内网自签证书场景才考虑 false。 |
| **Telegram 推送** | 通过 Telegram Bot 向个人、群组或 Topic 推送报告。 | 使用 @BotFather 创建 Bot，填写 Bot Token 和目标 Chat ID；群组 Topic 可额外填写 Thread ID。 |
| **邮件通知** | 通过 SMTP 邮箱发送分析报告。 | 填写发件邮箱、SMTP 授权码和收件人列表；多个收件人使用英文逗号分隔。 |
| **聊天平台 Bot** | 配置 Discord、Slack、Pushover、ServerChan 等聊天或推送平台。 | 按平台选择 Webhook 或 Bot Token 模式；Bot 模式通常还需要频道 ID。 |
| **报告输出设置** | 控制通知报告的详细程度、语言和模板输出。 | REPORT_TYPE 可选 simple/full/brief，REPORT_LANGUAGE 可选 zh/en。 |
| **通知渠道路由** | 为不同类型的通知指定目标推送渠道。 | 三个路由字段分别控制报告推送、告警推送和系统错误推送的目标渠道。从列表中勾选一个或多个渠道；全部不勾选则推送到所有已配置渠道。 |
| **通知去重与冷却** | 控制静态通知的去重时间窗口和冷却时间。 | NOTIFICATION_DEDUP_TTL_SECONDS 设定去重时间窗口，同一去重 key 在窗口内只推送一次；NOTIFICATION_COOLDOWN_SECONDS 设定冷却时间，同… |
| **静默时段** | 在指定时间段内抑制通知推送。 | NOTIFICATION_QUIET_HOURS 使用 HH:MM-HH:MM 格式，支持跨夜；NOTIFICATION_TIMEZONE 指定对应时区。 |
| **最低通知等级** | 过滤低于指定等级的静态通知。 | 设为 warning 时，只有 warning 及以上等级的通知会被推送；留空保留当前行为。 |
| **每日摘要（预留）** | 预留功能开关，当前不会发送每日摘要。 | 该字段为 P4 预留功能，当前开启后不会产生任何效果。 |

## Agent 行为

| 字段（界面标题） | 一句话说明 | 怎么用（摘要） |
| --- | --- | --- |
| **Agent 模式** | 启用 ReAct Agent 进行股票分析，替代普通分析流程。 | 开启后，系统使用多步推理 Agent 替代单轮 LLM 分析，可调用工具、检索新闻和执行复杂推理链路。 |
| **问股生成方式** | 决定问股助手用哪种方式生成回复，并配合工具查询行情、新闻和历史数据。 | 通常保持“自动”。系统会选择当前可用的方式来回答问题并调用数据工具；如果没有明确要固定方式，无需调整。 |
| **Agent 最大推理步数** | 控制 Agent 推理链路的最大步数上限。 | 设为默认值时，每个子 Agent 使用各自预设步数；调高后所有子 Agent 统一提升；调低后会裁剪子 Agent 的预设步数。 |
| **Agent 策略列表** | 指定 Agent 使用的策略技能列表。 | 使用英文逗号分隔策略名；留空使用默认策略（bull_trend）；设为 all 启用全部策略。 |
| **策略目录** | 存放 Agent 策略定义文件的目录。 | 填写相对于项目根目录的路径；目录内可放置 YAML 或 SKILL.md 格式的策略定义。 |
| **自然语言路由** | 允许 bot dispatcher 通过自然语言识别将股票查询路由到 Agent。 | 开启后，私聊中高置信度的股票相关消息（或群聊 @机器人）会自动路由到 Agent，无需显式命令。 |
| **Agent 架构** | 选择 Agent 执行架构。 | single 使用经典 ReAct 执行器；multi 使用编排器 pipeline，可分配多个专项子 Agent。 |
| **编排器模式** | 仅在 AGENT_ARCH=multi 时生效，控制 pipeline 包含哪些子 Agent。 | quick：技术→决策；standard：技术→情报→决策；full：技术→情报→风险→决策；specialist：full + 每策略专项 Agent。 |
| **Agent 超时** | Agent 执行的共享超时预算（秒）。 | single 模式下作为整体 ReAct 循环超时；multi 模式下作为协作 pipeline 总超时。设为 0 禁用超时。 |
| **风险 Agent 否决权** | 允许风险 Agent 在检测到关键风险信号时否决买入信号。 | 开启后，full/specialist 模式中的风险 Agent 可将买入建议降级为观望或卖出。 |
| **Deep Research** | 控制 Deep Research 的 token 预算和超时。 | AGENT_DEEP_RESEARCH_BUDGET 设定最大 token 预算；AGENT_DEEP_RESEARCH_TIMEOUT 设定超时秒数。 |
| **Agent 记忆系统** | 启用记忆与校准系统，跟踪 Agent 预测准确率并调整置信度。 | 开启后，系统会记录每次预测结果，与后续实际走势对比，用于校准未来分析的置信度。 |
| **策略自动权重** | 根据历史回测表现自动调整策略权重。 | 开启后，系统按各策略的历史回测准确率加权综合信号。 |
| **策略路由模式** | 控制策略选择方式。 | auto 模式根据市场环境自动检测并选择相关策略；manual 模式仅使用 AGENT_SKILLS 中手动指定的策略。 |
| **问股上下文压缩** | 控制问股可见对话历史的滚动摘要压缩，默认关闭以保持既有行为。 | AGENT_CONTEXT_COMPRESSION_ENABLED 开启后，仅压缩同一 session_id 下用户可见的 user/assistant 文本历史；profile 控制默认触发阈… |
| **事件监控** | 在定时模式下启用后台事件监控，定期轮询告警规则。 | AGENT_EVENT_MONITOR_ENABLED 开启后台监控；AGENT_EVENT_MONITOR_INTERVAL_MINUTES 设定轮询间隔（分钟）。 |
| **事件告警规则（Legacy JSON）** | 通过 JSON 数组配置基础价格和成交量告警规则。 | JSON 数组格式，每条规则包含 alert_type、stock_code 和条件字段。仅支持 price_cross、price_change_percent 和 volume_spike … |

## 报告

| 字段（界面标题） | 一句话说明 | 怎么用（摘要） |
| --- | --- | --- |
| **仅推送摘要** | 只推送分析摘要，不推送个股详情。适合跟踪大量股票时快速概览。 | 开启后，通知只包含整体摘要信息；关闭后包含每只股票的详细分析。 |
| **报告显示模型名** | 在报告页脚展示本次分析使用的 LLM 模型名称。 | 开启后，通知报告页脚会显示模型标识；关闭后隐藏。 |
| **报告模板目录** | Jinja2 报告模板的存放目录。 | 填写相对于项目根目录的路径；目录内放置 Jinja2 模板文件。 |
| **报告渲染引擎** | 启用 Jinja2 模板渲染引擎处理报告输出。 | 默认关闭；开启后报告会通过 Jinja2 模板渲染，支持自定义格式。 |
| **报告完整性校验** | LLM 输出后校验必填字段，缺失时重试或使用占位符。 | 开启后系统会检查报告是否包含必要的分析字段；REPORT_INTEGRITY_RETRY 控制重试次数。 |
| **历史信号对比** | 展示每只股票最近 N 次分析的信号对比。设为 0 关闭。 | 开启后，报告中会展示最近 N 次分析信号的对比表格。 |
| **逐股即时推送** | 每完成一只股票分析后立即推送，而不是等全部完成后批量推送。 | 开启后，每只股票分析完成后独立发送通知；关闭后汇总发送。 |
| **合并邮件通知** | 将个股分析与大盘复盘合并为一封邮件发送。 | 开启后，个股分析和大盘复盘会合并在同一封邮件中发送。 |

## 系统与安全

| 字段（界面标题） | 一句话说明 | 怎么用（摘要） |
| --- | --- | --- |
| **WebUI 监听地址** | 控制 WebUI 服务绑定在哪个网络地址上。 | 本机访问通常使用 127.0.0.1；云服务器、Docker 或需要外部访问时通常使用 0.0.0.0。 |
| **WebUI 端口** | 控制 WebUI 服务监听的端口。 | 本地默认 8000；如端口冲突可改为其他 1-65535 范围内端口。 |
| **日志目录** | 配置应用日志输出目录。 | 填写运行用户或容器可写的目录路径；本地默认 ./logs，容器内常见路径为 /app/logs。 |
| **默认启动 WebUI** | 控制启动期是否默认进入 WebUI/API 服务模式。 | 这是兼容旧启动入口的启动期配置；保存后不会让当前页面立即启动或关闭 WebUI。 |
| **启动前自动构建前端** | 控制后端启动 WebUI 前是否自动检查并构建前端静态产物。 | 源码部署通常保持 true；已预构建镜像、离线环境或受限环境可设为 false。 |
| **Web 登录保护** | 启用 WebUI 管理员密码保护。 | 请通过 WebUI 的认证设置入口启用或关闭；忘记密码可运行 python -m src.auth reset_password。 |
| **信任 X-Forwarded-For** | 在可信反向代理后使用 X-Forwarded-For 识别真实客户端 IP。 | 仅单层可信反向代理场景设为 true；直连公网保持 false。 |
| **定时任务** | 控制是否启用每日定时分析以及启动时是否立即执行一次。 | SCHEDULE_TIME 使用 HH:MM 24 小时格式；SCHEDULE_TIMES 可配置逗号分隔的多个 HH:MM 时间点；SCHEDULE_ENABLED 控制 runtime sc… |
| **启动后立即运行** | 控制非定时模式启动时是否立即执行一次分析。 | 需要只启动服务、不立即分析时设为 false。 |
| **交易日检查** | 控制非交易日是否跳过分析。 | 默认 true；需要强制运行可设为 false 或使用 --force-run。 |
| **网络代理** | 为外部 API、模型服务或搜索请求配置代理地址。 | 填写 http://host:port 形式；HTTPS_PROXY 可用于 HTTPS 请求代理。 |
| **日志级别** | 控制应用日志输出的详细程度。 | 可选 DEBUG、INFO、WARNING、ERROR、CRITICAL；级别越高输出越少。 |
| **调试模式** | 开启调试模式，输出详细日志信息。 | 开启后会输出更多内部状态和调试信息。 |
| **最大并发线程数** | 控制同时执行的股票分析线程数量。 | 设置并发分析的工作线程数；数值越高并发越高，但 API 限流风险也越大。 |
| **分析间隔** | 控制每只股票分析之间的间隔秒数，用于限速。 | 设为 0 无间隔；设为正值时每完成一只股票后等待指定秒数再分析下一只。 |
| **保存分析上下文快照** | 控制是否将分析历史的整份 context_snapshot 持久化到数据库。 | 默认开启。关闭后，新历史记录不会保存 enhanced_context、market_phase_summary、AnalysisContextPack overview 或运行诊断快照等 co… |
| **大盘分析** | 控制大盘分析功能的开关、支持的市场子集和配色方案。 | MARKET_REVIEW_ENABLED 开启大盘分析；DAILY_MARKET_CONTEXT_ENABLED 默认开启，会把当日大盘摘要用于个股分析 Prompt 与保守护栏；MARKET… |

## 回测

| 字段（界面标题） | 一句话说明 | 怎么用（摘要） |
| --- | --- | --- |
| **回测开关** | 启用或关闭历史分析回测功能。 | 开启后，系统会定期将历史分析结果与后续实际走势对比，评估策略准确率。 |
| **回测评估参数** | 控制回测评估窗口、最小记录年龄和中性回报带的参数组。 | BACKTEST_EVAL_WINDOW_DAYS 设定评估窗口（交易日数）；BACKTEST_MIN_AGE_DAYS 仅评估创建时间超过此天数的记录；BACKTEST_NEUTRAL_BAN… |
| **回测引擎版本** | 回测引擎版本标签。 | 一般无需修改；版本标签用于标识当前使用的回测逻辑版本。 |

## llm_channel

| 字段（界面标题） | 一句话说明 | 怎么用（摘要） |
| --- | --- | --- |
| **连接名称** | 为这个模型连接取一个唯一标识，用于在各使用场景中引用它。 | 只能使用小写字母、数字和下划线；建议使用能看出服务来源的名称。 |
| **连接协议** | 声明该连接使用哪类兼容协议。 | OpenAI Compatible 适合大多数中转和兼容服务；官方 Gemini/Anthropic/DeepSeek 可选择对应协议。 |
| **服务地址** | 该连接的接口根地址。 | OpenAI-compatible 服务通常填写以 /v1 结尾的地址；部分官方 SDK 连接可留空。 |
| **API 密钥** | 该连接调用模型服务所需的访问密钥。 | 单个密钥直接填写；多个密钥使用英文逗号分隔。 |
| **连接模型列表** | 声明该连接可供运行时选择的模型。 | 可点击“获取模型”从支持 /models 的连接拉取，也可手动填写逗号分隔列表。 |
| **运行时能力检测** | 手动验证当前连接模型是否支持 JSON、tools、stream 或 vision。 | 选择能力后点击检测；检测会发起真实 LLM 请求。 |
| **Temperature** | 运行时统一采样温度。 | 滑块范围 0 到 2；低值更稳定，高值更随机。 |
| **主要模型** | 普通分析流程默认使用的运行时模型。 | 从已启用连接的模型列表中选择；自动模式使用第一个可用模型。 |
| **Agent 主要模型** | Agent 场景专用的主要模型。 | 可选择独立模型；自动模式继承普通分析的主要模型。 |
| **备用模型** | 主要模型失败时使用的备用模型集合。 | 选择一个或多个模型；主要模型不会重复加入备用模型。 |
| **Vision 模型** | 用于截图识别、图像输入或视觉相关能力的模型。 | 选择支持图像输入的模型；自动模式跟随默认 Vision 逻辑。 |

## 相关

- [10 设置（操作教程）](10-settings.md)

- [客户端安装](../beginner-client-setup.md)

上一篇：[13 个股工作区](13-stock-details.md) · 下一篇：返回 [手册目录](README.md)
