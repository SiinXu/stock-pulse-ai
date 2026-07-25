# 14 設置字段速查（界面幫助匯總）


> 本頁為**繁體中文**操作手冊。產品介面亦可切換為繁體；若螢幕標籤與手冊不一致，**以介面為準**。

你好。這一章把設置頁裏**字段旁幫助文案**整理成速查表，方便你改某一項時先讀「是什麼 / 怎麼用」。

內容來自產品內嵌幫助（`settingsHelp`），與線上設置頁保持一致；若界面已改文案，**以屏幕為準**。

> 💡 第一次配置請仍按 [10 設置](10-settings.md) 的「先模型、再自選、再通知」走。本章是查字典，不是從零教程。

> ⚠️ 改配置請先**保存**再測試。密鑰不要截圖外傳。


## 基礎 / 自選與通用

| 字段（界面標題） | 一句話說明 | 怎麼用（摘要） |
| --- | --- | --- |
| **自選股列表** | 配置需要分析的股票代碼列表，是手動分析、定時任務和通知報告的基礎輸入。 | 多個股票代碼推薦使用英文逗號分隔；從表格或聊天中粘貼時，也會識別中文逗號、頓號、分號、空格和換行，並在保存後規範爲英文逗號。 |

## AI 與模型

| 字段（界面標題） | 一句話說明 | 怎麼用（摘要） |
| --- | --- | --- |
| **分析生成方式** | 決定系統用哪種方式生成個股分析、大盤復盤和普通文本回復。 | 通常保持「默認模型配置」。只有在本機已安裝並登錄對應 CLI，且你信任它處理分析內容時，才選擇本地 CLI 生成方式（實驗）。 |
| **備用生成方式** | 決定本地 CLI 生成失敗後，是直接報錯，還是再嘗試默認模型配置。 | 選擇「禁用」表示失敗就報錯；選擇「默認模型配置」表示再嘗試你已經配置好的普通模型。 |
| **OpenCode CLI 模型** | 可選：指定 StockPulse 調用 OpenCode run 時傳給 --model 的模型名。 | 僅在「分析生成方式」選擇 OpenCode CLI 時生效。留空時 StockPulse 不傳 --model，使用你本機 OpenCode 的默認模型配置。 |
| **生成超時（秒）** | 限制一次模型生成最多等待多久。 | 默認 300 秒，主要用於本地 CLI 這類命令行生成方式。 |
| **最大輸出大小（字節）** | 限制一次本地命令行生成可讀取的輸出大小。 | 默認 1048576 字節。超過限制時會停止解析，並記錄「輸出過大」錯誤。 |
| **模型生成最大並發** | 限制同時進行的模型生成任務數量。 | 默認 1。使用本地 CLI 生成方式時，實際並發還會受「本地命令行最大並發」限制。 |
| **本地命令行最大並發** | 限制同時啓動多少個本地命令行生成進程。 | 默認 1，避免同時啓動多個本地 CLI 進程導致機器變慢或輸出互相干擾。 |
| **主要模型** | 指定普通分析流程默認使用的模型。 | 從可用模型中選擇；留空時系統會根據已配置的模型連接自動選擇。 |
| **LLM 連接列表** | 聲明多個模型連接，用於多 provider、多 Key、備用模型和可視化連接管理。 | 填寫逗號分隔的連接名，例如 deepseek,aihubmix；每個連接再配置 LLM_<NAME>_BASE_URL、LLM_<NAME>_API_KEY(S)、LLM_<NAME>_MODE… |
| **Agent 主要模型** | 爲問股、策略 Agent 等 Agent 場景單獨指定模型。 | 從可用模型中選擇；留空時繼承普通分析的主要模型。 |
| **Vision 模型** | 爲圖片理解任務選擇模型。 | 從可用模型中選擇；留空時使用系統默認策略。 |
| **備用模型** | 主要模型失敗時按順序嘗試的備用模型列表。 | 從可用模型中選擇一個或多個，按順序嘗試。 |
| **高級模型路由 YAML** | 指定 LiteLLM 原生 YAML 路由文件，適合複雜路由、限流和專家配置。 | 填寫項目可訪問的 YAML 文件路徑，例如 ./litellm_config.yaml。 |
| **模型配置來源模式** | 選擇當前生效的模型配置來源。 | auto 保持歷史優先級（YAML > Channels > legacy）；channels/yaml/legacy 只強制單一來源。 |
| **Temperature** | 控制模型輸出隨機性。 | 取值範圍 0.0 到 2.0；越低越穩定，越高越發散。 |
| **Prompt Cache 遙測** | 記錄 provider 返回的 prompt cache usage 與歸一化診斷。 | 默認開啓。關閉後不持久化 provider raw usage JSON、normalized cache fields 和 cache decision diagnostics，基礎 toke… |
| **Prompt Cache Hints** | 允許主分析路徑主動發送已驗證 provider-specific cache hint。 | 默認關閉。開啓後仍只會對 registry 中 verified 或 smoke-tested 的 provider/route 發送 prompt_cache_key、cache_contro… |
| **Prompt Cache 診斷級別** | 控制 prompt cache capability 與 hint 決策診斷細節。 | 可選 off、basic 或 debug。非法值會回退爲 off。 |
| **LLM 用量 HMAC 密鑰** | 用於 LLM usage telemetry 的 message-level HMAC 指紋。 | 通常留空即可，系統會在數據目錄生成本地密鑰文件；只有需要跨部署比較 HMAC 時才手動配置同一個高熵隨機密鑰，例如 openssl rand -hex 32。 |
| **LLM 用量 HMAC 版本** | 標記當前 LLM usage HMAC 密鑰版本。 | 輪換 LLM_USAGE_HMAC_SECRET 時同步更新，例如 prod-2026-06。 |
| **模型服務 API Key** | 配置模型服務商或聚合網關的訪問密鑰。 | 在對應服務商控制臺創建 API Key 後填入；如需輪換或負載均衡，對應的多 Key 變體字段使用英文逗號分隔。 |
| **Anspire LLM 網關** | 使用 Anspire API Key 作爲 OpenAI-compatible 模型網關的兼容入口。 | ANSPIRE_LLM_ENABLED 控制是否啓用該兼容路徑；ANSPIRE_LLM_BASE_URL 指定網關地址；ANSPIRE_LLM_MODEL 指定未顯式選擇主要模型時的默認模型。 |
| **Legacy Provider 參數** | 爲舊版 provider 專用配置路徑設置模型名、溫度或 token 上限。 | 這些字段用於兼容歷史配置；新配置優先使用 LITELLM_MODEL、LITELLM_FALLBACK_MODELS、VISION_MODEL、LLM_TEMPERATURE 或 LLM Cha… |
| **OpenAI 兼容 Base URL** | 指定 OpenAI-compatible 服務的接口根地址。 | 通常以 /v1 結尾；官方接口、中轉網關和本地兼容服務的地址各不相同。 |

## 數據源

| 字段（界面標題） | 一句話說明 | 怎麼用（摘要） |
| --- | --- | --- |
| **Tushare Token** | 用於訪問 Tushare Pro 數據接口。 | 在 Tushare 賬戶中獲取 token 後填入。 |
| **TickFlow API Key** | 用於啓用 TickFlow A 股日 K、實時行情、股票列表/名稱與大盤復盤增強數據。 | 在 TickFlow 獲取 API Key 後填入；未配置時系統會繼續使用其他可用數據源和降級路徑。 |
| **TickFlow 日 K 優先級** | 控制 TickFlow 在 A 股日 K 數據源回退鏈中的位置。 | 填寫整數；數字越小越早嘗試，默認 2。未配置 TICKFLOW_API_KEY 時該優先級不會生效。 |
| **TickFlow 日 K 復權模式** | 控制 TickFlow 日 K 線的復權口徑。 | 可選 none、forward、backward、forward_additive 或 backward_additive。默認 none。 |
| **TickFlow 批量日 K 預取** | 控制批量分析時是否先用 TickFlow 批量接口預熱日 K 緩存。 | 默認開啓。如果當前套餐沒有批量日 K 權限，系統會短期記住失敗狀態並繼續回退。 |
| **TickFlow 批量大小** | 控制 TickFlow 日 K 和實時行情批量請求的單批最大標的數。 | 填寫正整數，默認 100。標的數超過該值時系統會拆分多批請求。 |
| **股票索引遠程更新** | 從 GitHub main 分支獲取最新股票自動補全索引，並緩存到本地。 | 默認開啓；如運行環境無法訪問 GitHub raw，可關閉開關。遠程 URL、檢查頻率和超時時間均爲系統內置值。 |
| **AlphaSift 選股** | 控制是否啓用內置 AlphaSift 選股頁。 | 默認關閉。設爲 true 後，Web 會檢查隨後端依賴安裝的 alphasift.dsa_adapter；若缺失，請在倉庫根目錄依次運行 python -m pip install --upgr… |
| **AlphaSift 安裝來源** | 配置顯式修復安裝使用的受信任 AlphaSift pip 來源。 | 默認固定到已驗證的 ZhuLinsen/alphasift commit；正常部署通過 requirements 安裝，只有手動調用修復安裝入口時才使用該來源。 |
| **實時行情源優先級** | 配置多個實時行情源的嘗試順序。 | 優先級使用英文逗號分隔；系統會按順序嘗試可用數據源。 |
| **實時行情配置** | 控制實時行情和盤中技術指標是否啓用。 | 開關字段使用 true/false；行情源順序由 REALTIME_SOURCE_PRIORITY 單獨配置。 |
| **搜索服務 API Key** | 配置新聞與搜索增強所需的第三方搜索服務密鑰。 | 多 Key 字段使用英文逗號分隔；系統會按現有搜索優先級和可用性選擇服務。 |
| **SearXNG 實例地址** | 配置自建或可信 SearXNG 搜索實例。 | 多個實例使用英文逗號分隔；自建實例需要啓用 JSON 輸出格式。 |
| **籌碼分布分析** | 控制是否啓用籌碼分布相關分析。 | 雲部署或數據源不穩定時可設爲 false。 |
| **乖離率閾值** | 設置股價偏離 MA5 的風險提示閾值。 | 填寫百分比數值；當價格偏離 MA5 超過閾值時，報告會提示避免追高或注意回歸風險。 |
| **Pytdx 通達信服務器** | 配置通達信行情服務器地址，覆蓋內置默認服務器。 | 可分別填寫 PYTDX_HOST/PYTDX_PORT，也可使用 PYTDX_SERVERS 填寫多個 ip:port；PYTDX_SERVERS 優先級更高。 |
| **新聞時間窗口** | 控制納入分析上下文的新聞時效範圍。 | NEWS_MAX_AGE_DAYS 設最大天數，NEWS_STRATEGY_PROFILE 設窗口策略。 |

## 通知

| 字段（界面標題） | 一句話說明 | 怎麼用（摘要） |
| --- | --- | --- |
| **飛書羣機器人 Webhook** | 配置飛書自定義羣機器人，用於把分析報告推送到指定飛書羣。 | 在飛書羣中添加自定義機器人後，複製 open-apis/bot/v2/hook 開頭的 Webhook URL 到這裡。 |
| **飛書 Stream 模式** | 啓用飛書應用機器人 / Stream Bot 長連接模式，不是飛書羣 Webhook 推送開關。 | 只有在已創建飛書應用、完成應用發布、權限和事件訂閱配置後才開啓；同時需要 FEISHU_APP_ID 和 FEISHU_APP_SECRET。 |
| **飛書 App Bot 推送目標** | 配置飛書應用機器人主動推送的目標 chat_id（羣聊模式）或 open_id（私聊模式）。 | 需要同時填寫 FEISHU_APP_ID 和 FEISHU_APP_SECRET。羣聊模式填寫 oc_ 開頭的 chat_id；私聊模式填寫 ou_ 開頭的 open_id 並將 FEISHU_… |
| **飛書接收方 ID 類型** | 指定 FEISHU_CHAT_ID 的類型：chat_id 表示羣聊，open_id 表示私聊。 | 羣聊選擇 chat_id；私聊（給指定用戶發 P2P 消息）選擇 open_id。 |
| **飛書 API 域名** | 選擇飛書 API 的區域：feishu 對應飛書國內版（feishu.cn），lark 對應 Lark 國際版（larksuite.com）。 | 國內用戶選擇 feishu；海外 / Lark 用戶選擇 lark。 |
| **釘釘 Stream 模式** | 啓用釘釘應用機器人長連接模式，不是普通釘釘羣機器人 Webhook 開關。 | 需要先在釘釘開放平臺配置應用機器人，並填寫 DINGTALK_APP_KEY 和 DINGTALK_APP_SECRET。 |
| **企業微信 Webhook** | 配置企業微信羣機器人 Webhook，用於把分析報告推送到指定羣。 | 在企業微信羣中創建機器人後，複製 qyapi.weixin.qq.com/cgi-bin/webhook/send 開頭的 Webhook URL。 |
| **自定義 Webhook** | 向任意支持 POST JSON 的服務推送報告。 | 多個 URL 使用英文逗號分隔；如需自定義 body，可配置 CUSTOM_WEBHOOK_BODY_TEMPLATE。 |
| **Webhook SSL 校驗** | 控制發送 HTTPS Webhook 時是否校驗證書。 | 默認保持 true；只有可信內網自籤證書場景才考慮 false。 |
| **Telegram 推送** | 通過 Telegram Bot 向個人、羣組或 Topic 推送報告。 | 使用 @BotFather 創建 Bot，填寫 Bot Token 和目標 Chat ID；羣組 Topic 可額外填寫 Thread ID。 |
| **郵件通知** | 通過 SMTP 郵箱發送分析報告。 | 填寫發件郵箱、SMTP 授權碼和收件人列表；多個收件人使用英文逗號分隔。 |
| **聊天平臺 Bot** | 配置 Discord、Slack、Pushover、ServerChan 等聊天或推送平臺。 | 按平臺選擇 Webhook 或 Bot Token 模式；Bot 模式通常還需要頻道 ID。 |
| **報告輸出設置** | 控制通知報告的詳細程度、語言和模板輸出。 | REPORT_TYPE 可選 simple/full/brief，REPORT_LANGUAGE 可選 zh/en。 |
| **通知渠道路由** | 爲不同類型的通知指定目標推送渠道。 | 三個路由字段分別控制報告推送、告警推送和系統錯誤推送的目標渠道。從列表中勾選一個或多個渠道；全部不勾選則推送到所有已配置渠道。 |
| **通知去重與冷卻** | 控制靜態通知的去重時間窗口和冷卻時間。 | NOTIFICATION_DEDUP_TTL_SECONDS 設定去重時間窗口，同一去重 key 在窗口內只推送一次；NOTIFICATION_COOLDOWN_SECONDS 設定冷卻時間，同… |
| **靜默時段** | 在指定時間段內抑制通知推送。 | NOTIFICATION_QUIET_HOURS 使用 HH:MM-HH:MM 格式，支持跨夜；NOTIFICATION_TIMEZONE 指定對應時區。 |
| **最低通知等級** | 過濾低於指定等級的靜態通知。 | 設爲 warning 時，只有 warning 及以上等級的通知會被推送；留空保留當前行爲。 |
| **每日摘要（預留）** | 預留功能開關，當前不會發送每日摘要。 | 該字段爲 P4 預留功能，當前開啓後不會產生任何效果。 |

## Agent 行爲

| 字段（界面標題） | 一句話說明 | 怎麼用（摘要） |
| --- | --- | --- |
| **Agent 模式** | 啓用 ReAct Agent 進行股票分析，替代普通分析流程。 | 開啓後，系統使用多步推理 Agent 替代單輪 LLM 分析，可調用工具、檢索新聞和執行複雜推理鏈路。 |
| **問股生成方式** | 決定問股助手用哪種方式生成回復，並配合工具查詢行情、新聞和歷史數據。 | 通常保持「自動」。系統會選擇當前可用的方式來回答問題並調用數據工具；如果沒有明確要固定方式，無需調整。 |
| **Agent 最大推理步數** | 控制 Agent 推理鏈路的最大步數上限。 | 設爲默認值時，每個子 Agent 使用各自預設步數；調高后所有子 Agent 統一提升；調低後會裁剪子 Agent 的預設步數。 |
| **Agent 策略列表** | 指定 Agent 使用的策略技能列表。 | 使用英文逗號分隔策略名；留空使用默認策略（bull_trend）；設爲 all 啓用全部策略。 |
| **策略目錄** | 存放 Agent 策略定義文件的目錄。 | 填寫相對於項目根目錄的路徑；目錄內可放置 YAML 或 SKILL.md 格式的策略定義。 |
| **自然語言路由** | 允許 bot dispatcher 通過自然語言識別將股票查詢路由到 Agent。 | 開啓後，私聊中高置信度的股票相關消息（或羣聊 @機器人）會自動路由到 Agent，無需顯式命令。 |
| **Agent 架構** | 選擇 Agent 執行架構。 | single 使用經典 ReAct 執行器；multi 使用編排器 pipeline，可分配多個專項子 Agent。 |
| **編排器模式** | 僅在 AGENT_ARCH=multi 時生效，控制 pipeline 包含哪些子 Agent。 | quick：技術→決策；standard：技術→情報→決策；full：技術→情報→風險→決策；specialist：full + 每策略專項 Agent。 |
| **Agent 超時** | Agent 執行的共享超時預算（秒）。 | single 模式下作爲整體 ReAct 循環超時；multi 模式下作爲協作 pipeline 總超時。設爲 0 禁用超時。 |
| **風險 Agent 否決權** | 允許風險 Agent 在檢測到關鍵風險信號時否決買入信號。 | 開啓後，full/specialist 模式中的風險 Agent 可將買入建議降級爲觀望或賣出。 |
| **Deep Research** | 控制 Deep Research 的 token 預算和超時。 | AGENT_DEEP_RESEARCH_BUDGET 設定最大 token 預算；AGENT_DEEP_RESEARCH_TIMEOUT 設定超時秒數。 |
| **Agent 記憶系統** | 啓用記憶與校準系統，跟蹤 Agent 預測準確率並調整置信度。 | 開啓後，系統會記錄每次預測結果，與後續實際走勢對比，用於校準未來分析的置信度。 |
| **策略自動權重** | 根據歷史回測表現自動調整策略權重。 | 開啓後，系統按各策略的歷史回測準確率加權綜合信號。 |
| **策略路由模式** | 控制策略選擇方式。 | auto 模式根據市場環境自動檢測並選擇相關策略；manual 模式僅使用 AGENT_SKILLS 中手動指定的策略。 |
| **問股上下文壓縮** | 控制問股可見對話歷史的滾動摘要壓縮，默認關閉以保持既有行爲。 | AGENT_CONTEXT_COMPRESSION_ENABLED 開啓後，僅壓縮同一 session_id 下用戶可見的 user/assistant 文本歷史；profile 控制默認觸發閾… |
| **事件監控** | 在定時模式下啓用後臺事件監控，定期輪詢告警規則。 | AGENT_EVENT_MONITOR_ENABLED 開啓後臺監控；AGENT_EVENT_MONITOR_INTERVAL_MINUTES 設定輪詢間隔（分鐘）。 |
| **事件告警規則（Legacy JSON）** | 通過 JSON 數組配置基礎價格和成交量告警規則。 | JSON 數組格式，每條規則包含 alert_type、stock_code 和條件字段。僅支持 price_cross、price_change_percent 和 volume_spike … |

## 報告

| 字段（界面標題） | 一句話說明 | 怎麼用（摘要） |
| --- | --- | --- |
| **僅推送摘要** | 只推送分析摘要，不推送個股詳情。適合跟蹤大量股票時快速概覽。 | 開啓後，通知只包含整體摘要信息；關閉後包含每隻股票的詳細分析。 |
| **報告顯示模型名** | 在報告頁腳展示本次分析使用的 LLM 模型名稱。 | 開啓後，通知報告頁腳會顯示模型標識；關閉後隱藏。 |
| **報告模板目錄** | Jinja2 報告模板的存放目錄。 | 填寫相對於項目根目錄的路徑；目錄內放置 Jinja2 模板文件。 |
| **報告渲染引擎** | 啓用 Jinja2 模板渲染引擎處理報告輸出。 | 默認關閉；開啓後報告會通過 Jinja2 模板渲染，支持自定義格式。 |
| **報告完整性校驗** | LLM 輸出後校驗必填字段，缺失時重試或使用佔位符。 | 開啓後系統會檢查報告是否包含必要的分析字段；REPORT_INTEGRITY_RETRY 控制重試次數。 |
| **歷史信號對比** | 展示每隻股票最近 N 次分析的信號對比。設爲 0 關閉。 | 開啓後，報告中會展示最近 N 次分析信號的對比表格。 |
| **逐股即時推送** | 每完成一隻股票分析後立即推送，而不是等全部完成後批量推送。 | 開啓後，每隻股票分析完成後獨立發送通知；關閉後匯總發送。 |
| **合併郵件通知** | 將個股分析與大盤復盤合併爲一封郵件發送。 | 開啓後，個股分析和大盤復盤會合併在同一封郵件中發送。 |

## 系統與安全

| 字段（界面標題） | 一句話說明 | 怎麼用（摘要） |
| --- | --- | --- |
| **WebUI 監聽地址** | 控制 WebUI 服務綁定在哪個網絡地址上。 | 本機訪問通常使用 127.0.0.1；雲服務器、Docker 或需要外部訪問時通常使用 0.0.0.0。 |
| **WebUI 端口** | 控制 WebUI 服務監聽的端口。 | 本地默認 8000；如端口衝突可改爲其他 1-65535 範圍內端口。 |
| **日誌目錄** | 配置應用日誌輸出目錄。 | 填寫運行用戶或容器可寫的目錄路徑；本地默認 ./logs，容器內常見路徑爲 /app/logs。 |
| **默認啓動 WebUI** | 控制啓動期是否默認進入 WebUI/API 服務模式。 | 這是兼容舊啓動入口的啓動期配置；保存後不會讓當前頁面立即啓動或關閉 WebUI。 |
| **啓動前自動構建前端** | 控制後端啓動 WebUI 前是否自動檢查並構建前端靜態產物。 | 源碼部署通常保持 true；已預構建鏡像、離線環境或受限環境可設爲 false。 |
| **Web 登錄保護** | 啓用 WebUI 管理員密碼保護。 | 請通過 WebUI 的認證設置入口啓用或關閉；忘記密碼可運行 python -m src.auth reset_password。 |
| **信任 X-Forwarded-For** | 在可信反向代理後使用 X-Forwarded-For 識別真實客戶端 IP。 | 僅單層可信反向代理場景設爲 true；直連公網保持 false。 |
| **定時任務** | 控制是否啓用每日定時分析以及啓動時是否立即執行一次。 | SCHEDULE_TIME 使用 HH:MM 24 小時格式；SCHEDULE_TIMES 可配置逗號分隔的多個 HH:MM 時間點；SCHEDULE_ENABLED 控制 runtime sc… |
| **啓動後立即運行** | 控制非定時模式啓動時是否立即執行一次分析。 | 需要只啓動服務、不立即分析時設爲 false。 |
| **交易日檢查** | 控制非交易日是否跳過分析。 | 默認 true；需要強制運行可設爲 false 或使用 --force-run。 |
| **網絡代理** | 爲外部 API、模型服務或搜索請求配置代理地址。 | 填寫 http://host:port 形式；HTTPS_PROXY 可用於 HTTPS 請求代理。 |
| **日誌級別** | 控制應用日誌輸出的詳細程度。 | 可選 DEBUG、INFO、WARNING、ERROR、CRITICAL；級別越高輸出越少。 |
| **調試模式** | 開啓調試模式，輸出詳細日誌信息。 | 開啓後會輸出更多內部狀態和調試信息。 |
| **最大並發線程數** | 控制同時執行的股票分析線程數量。 | 設置並發分析的工作線程數；數值越高並發越高，但 API 限流風險也越大。 |
| **分析間隔** | 控制每隻股票分析之間的間隔秒數，用於限速。 | 設爲 0 無間隔；設爲正值時每完成一隻股票後等待指定秒數再分析下一隻。 |
| **保存分析上下文快照** | 控制是否將分析歷史的整份 context_snapshot 持久化到數據庫。 | 默認開啓。關閉後，新歷史記錄不會保存 enhanced_context、market_phase_summary、AnalysisContextPack overview 或運行診斷快照等 co… |
| **大盤分析** | 控制大盤分析功能的開關、支持的市場子集和配色方案。 | MARKET_REVIEW_ENABLED 開啓大盤分析；DAILY_MARKET_CONTEXT_ENABLED 默認開啓，會把當日大盤摘要用於個股分析 Prompt 與保守護欄；MARKET… |

## 回測

| 字段（界面標題） | 一句話說明 | 怎麼用（摘要） |
| --- | --- | --- |
| **回測開關** | 啓用或關閉歷史分析回測功能。 | 開啓後，系統會定期將歷史分析結果與後續實際走勢對比，評估策略準確率。 |
| **回測評估參數** | 控制回測評估窗口、最小記錄年齡和中性回報帶的參數組。 | BACKTEST_EVAL_WINDOW_DAYS 設定評估窗口（交易日數）；BACKTEST_MIN_AGE_DAYS 僅評估創建時間超過此天數的記錄；BACKTEST_NEUTRAL_BAN… |
| **回測引擎版本** | 回測引擎版本標籤。 | 一般無需修改；版本標籤用於標識當前使用的回測邏輯版本。 |

## llm_channel

| 字段（界面標題） | 一句話說明 | 怎麼用（摘要） |
| --- | --- | --- |
| **連接名稱** | 爲這個模型連接取一個唯一標識，用於在各使用場景中引用它。 | 只能使用小寫字母、數字和下劃線；建議使用能看出服務來源的名稱。 |
| **連接協議** | 聲明該連接使用哪類兼容協議。 | OpenAI Compatible 適合大多數中轉和兼容服務；官方 Gemini/Anthropic/DeepSeek 可選擇對應協議。 |
| **服務地址** | 該連接的接口根地址。 | OpenAI-compatible 服務通常填寫以 /v1 結尾的地址；部分官方 SDK 連接可留空。 |
| **API 密鑰** | 該連接調用模型服務所需的訪問密鑰。 | 單個密鑰直接填寫；多個密鑰使用英文逗號分隔。 |
| **連接模型列表** | 聲明該連接可供運行時選擇的模型。 | 可點擊「獲取模型」從支持 /models 的連接拉取，也可手動填寫逗號分隔列表。 |
| **運行時能力檢測** | 手動驗證當前連接模型是否支持 JSON、tools、stream 或 vision。 | 選擇能力後點擊檢測；檢測會發起真實 LLM 請求。 |
| **Temperature** | 運行時統一採樣溫度。 | 滑塊範圍 0 到 2；低值更穩定，高值更隨機。 |
| **主要模型** | 普通分析流程默認使用的運行時模型。 | 從已啓用連接的模型列表中選擇；自動模式使用第一個可用模型。 |
| **Agent 主要模型** | Agent 場景專用的主要模型。 | 可選擇獨立模型；自動模式繼承普通分析的主要模型。 |
| **備用模型** | 主要模型失敗時使用的備用模型集合。 | 選擇一個或多個模型；主要模型不會重複加入備用模型。 |
| **Vision 模型** | 用於截圖識別、圖像輸入或視覺相關能力的模型。 | 選擇支持圖像輸入的模型；自動模式跟隨默認 Vision 邏輯。 |

## 相關

- [10 設置（操作教程）](10-settings.md)

- [小白客戶端安裝](../../../beginner-client-setup.md)


上一篇：[13 個股工作區](13-stock-details.md) · 下一篇：返回 [手冊目錄](README.md)
