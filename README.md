# astrbot_plugin_browser_llm

Agent 驱动的安全只读网页浏览插件。管理员可以让 LLM 使用真实浏览器联网搜索、阅读网页、滚动、截图并核实来源；默认不允许登录、填表、提交或下载。

## ✨ 功能特性

- **工具化子代理架构**：主 LLM 只看到 `browse_web`，默认只读子代理获得 16 个浏览工具，降低主模型 token 占用
- **可靠触发**：明确说“联网搜索/上网查/查询最新资料”时要求主模型调用浏览器；`/browse <任务>` 可直接强制执行
- **安全只读默认值**：工具集层移除输入、提交、按钮/坐标点击、表单控件操作和媒体下载，不只依赖提示词
- **管理员双门禁**：插件强制 `event.is_admin()`，同时支持 AstrBot WebUI 工具权限与会话黑白名单
- **系统 Chrome**：可通过 `browser_executable_path` 复用已安装的 Chrome，并保留 Chrome 沙箱
- **识图辅助**：接入多模态模型（如 opencode-go/mimo-v2.5）对截图做视觉理解，支持区域裁剪放大识图（`browse_zoom_crop`）
- **媒体嗅探**：从页面嗅探图片/视频资源，下载并发送到群聊（`browse_sniff_media`）
- **本地页面自检**：`browse_local_page` 渲染查看本地 HTML 供子代理/开发者自检页面（无头渲染 + 截图 + 视觉描述，视觉不可用时降级文本提取；路径白名单为工作区（AstrBot 工作区 + 平台工作区，如 `/root/workspace`）+ 插件 data 目录，可用环境变量 `BROWSER_LLM_EXTRA_LOCAL_ROOTS`（冒号分隔）追加额外根目录；支持 `perception` 参数按任务控制感知方式——全文本子代理读文档/报错页可传 `perception="text"` 跳过截图识图）
- **静默模式**：浏览截图仅内部识图，不往群聊刷图（`silent_mode`）
- **感知模式精细化**：页面感知方式可精确控制——`browse_web` 参数级前缀 `perception=text|text_image|image` 按任务覆盖、`perception_rules` 按会话（UMO 子串匹配）设定默认、全局 `page_perception` 兜底；全文本子代理（前端/测试等）不再为每次浏览付出截图识图开销
- **识图缓存**：同一 URL（去 fragment/尾斜杠规范化）在 `vision_cache_ttl` 内重复识图直接复用结果（带 `[缓存]` 前缀），省识图耗时与 token
- **配置热更新**：会话黑白名单、内容禁词、内网拦截开关、截图开关、识图 Provider、感知规则等修改后无需重启，下次工具调用即生效（Dashboard 保存即同步）
- **资源清理加固**：浏览器关闭/插件重载带超时保护与总超时兜底，避免 WebUI 重载后旧实例 chromium 残留进程
- **安全防护**：SSRF 内网/云元数据拦截、内容过滤、图形验证码自动停止和会话资源上限

## 🏗️ 架构

```
主 LLM（main agent）
  ├── browse_web（网页浏览入口 llm_tool）
  │     └── 子代理 tool_loop_agent（默认 16 个只读 browse_* 工具）
  │           ├── Playwright 浏览器（chromium）
  │           ├── SessionManager（会话/标签页隔离）
  │           ├── SafetyFilter（SSRF/禁词）
  │           └── 多模态识图（vision_provider_id）
  └── browse_local_page（本地 HTML 渲染查看入口 llm_tool，供子代理/开发者自检）
        ├── 无头渲染（独立页面，用完即关）
        ├── 路径白名单（工作区 + 插件 data 目录）
        └── 视觉描述 / 降级文本提取
```

## 📦 安装

将插件目录放入 `AstrBot/data/plugins/`，重启 AstrBot 或在 WebUI 重载插件。

依赖：Python Playwright 1.62.0。推荐安装系统 Chrome 后设置绝对路径；不需要执行
`playwright install chromium`。已验证 AstrBot v4.27.3、Google Chrome 152、
Discord 与 QQ 官方适配器。

## ⚙️ 配置项（WebUI 插件配置）

| 配置 | 默认 | 说明 |
|---|---|---|
| `browser_type` | chromium | 浏览器内核（chromium/firefox/webkit，`chrome` 自动映射为 chromium；非法值启动前给出可选值提示） |
| `browser_executable_path` | - | 系统 Chrome/Chromium 的绝对路径；非空时仅支持 chromium |
| `read_only_mode` | true | 移除可能修改网站状态或下载内容的工具 |
| `enable_local_page_preview` | false | 是否允许管理员渲染白名单目录中的本地 HTML |
| `default_url` | https://www.baidu.com | 新会话首个标签的初始页 |
| `default_search_engine` | 必应搜索 | 默认搜索引擎（必应搜索/百度搜索/谷歌搜索/B站搜索） |
| `max_chars` | 4000 | 正文摘要最大字符数（<=0 用默认值） |
| `max_links` | 20 | 链接列表最多返回条数（<=0 用默认值） |
| `timeout` | 30 | 页面加载超时（秒） |
| `max_pages` | 5 | 全部会话的标签页总数上限 |
| `idle_timeout` | 1800 | 会话空闲回收阈值（秒） |
| `session_whitelist` | [] | 管理员会话白名单（空=允许所有 AstrBot 管理员） |
| `session_blacklist` | [] | 禁止使用浏览器的会话黑名单 |
| `enable_screenshot` | true | 是否允许截图 |
| `silent_mode` | true | 静默模式：截图仅内部识图不发群 |
| `page_perception` | text_image | 全局页面感知方式：text / text_image / image |
| `perception_rules` | [] | 会话级感知规则：按 UMO 子串匹配（不区分大小写）设定会话默认感知方式。每条规则含 `match`、`perception`（text/text_image/image）、可选 `note`；命中第一条生效。优先级：browse_web 前缀 > 规则 > 全局。例：`[{"match":"tester","perception":"text","note":"测试子代理只需正文"}]` |
| `vision_cache_ttl` | 60 | 识图短时缓存秒数：同 URL（去 fragment/尾斜杠）+ 同会话在 TTL 内重复识图复用结果（返回带 `[缓存]` 前缀）；0 关闭 |
| `vision_provider_id` | - | 多模态识图模型 Provider ID。下拉选项自动同步 AstrBot 已配置的聊天模型 Provider（启动时与每次识图调用时刷新）；留空则截图仅发用户不做识图 |
| `vision_prompt` | - | 自定义识图提示词 |
| `cache_days` | 3 | 媒体缓存保留天数，超期自动清理；0 或负值 = 不清理 |
| `proxy` | - | 浏览器代理（如 http://127.0.0.1:7890），留空直连 |
| `viewport` | 1280×800 | 浏览器视口尺寸 |
| `agent_max_steps` | 70 | 子代理单次委托最大工具步数 |
| `agent_tool_timeout` | 1200 | 子代理单次工具超时（秒） |
| `banned_words` | 11 词 | 内容禁词过滤：URL / 搜索关键词 / 本地页面 / 网页正文与标题 / browse_web 任务描述命中均拒绝返回 |
| `block_internal_ip` | true | SSRF 防护（拦截内网/环回/云元数据地址） |

> 类型健壮性（v1.3.1）：数值/布尔配置遇非法值（字符串、None、类型错误）自动回退
> schema 默认值并记录警告，手动编辑 config.json 不会导致插件加载失败；字符串
> `"false"`/`"0"`/`"off"` 按布尔 false 归一，不再被强转 True。

## 🎯 感知模式控制（v1.3.0）

感知模式决定浏览器子代理「用文字还是截图」理解页面，三处控制点，优先级从高到低：

1. **工具参数级（按任务覆盖）**：`browse_web` 的 `input` 开头加前缀
   `perception=text|text_image|image`（大小写不敏感，后跟空格或换行再接任务描述），
   仅本次任务生效。例：`perception=text 打开 https://example.com 读取正文`
   （纯文字模式，绝对不触发截图识图，适合读文档/查报错/看代码）；
   `perception=image 看看这个页面长什么样`（截图为主）。
   非法值（如 `perception=foo`）会被忽略并记录告警，回落到规则/全局配置。
2. **会话规则级（按 UMO 默认）**：配置 `perception_rules`，按会话 UMO 子串匹配
   （不区分大小写）设定默认模式，命中第一条生效。例：
   `[{"match": "tester", "perception": "text"}]` 后，UMO 含 `tester` 的会话
   （如测试子代理）默认纯文字浏览。
3. **全局默认**：`page_perception`（text / text_image / image）。

**子代理本地页面工具（v1.3.0 补强）**：`browse_local_page` 同样支持感知模式控制。
子代理无独立 UMO（继承调用方会话），`perception_rules` 按 UMO 子串无法区分子代理，
故本地页面工具仅支持**工具参数级**控制：可选参数 `perception=text|text_image|image`
（大小写不敏感，可省略；缺省或非法值时跟随全局 `page_perception`，再回落
text_image）。全文本子代理（前端/测试/工程等）读取本地 HTML 文档、报错页时传
`perception="text"`，仅做页面文本提取——跳过截图与识图调用，零识图耗时/token
开销、不落盘截图文件；`text_image` 为默认（文本 + 截图识图）；`image` 以截图识图
为主、页面文本为辅（识图缓存正常生效）。例：`browse_local_page(path=..., perception="text")`。

## 🚀 使用示例

自然语言明确要求联网时，主模型会优先委托浏览器；工具选择仍由 LLM 完成。需要确定性执行时使用 `/browse`：

- 「联网搜索 AstrBot 最新版本，并给出来源」
- 「打开 https://example.com 读取正文」
- `/browse 搜索 Playwright 最新版本，交叉核实两个来源`
- `/browse perception=text_image 打开这个网址并截图说明页面结构`

普通成员不能调用浏览器。只读模式不会登录、填写或提交表单、点击操作按钮、下载文件或尝试通过验证码。

## 🧪 开发与测试

```bash
cd astrbot_plugin_browser_llm
python -m pytest tests/ -q    # 全量测试（390 passed，2 个可选浏览器集成测试跳过）
```

测试覆盖：工具契约（docstring 与注册一致性）、感知模式前缀解析/规则匹配/优先级、
识图缓存（TTL/URL 规范化/会话隔离/拒识不写缓存）、本地页面工具（感知参数/路径白名单/
降级文本）、SSRF 与安全过滤、配置热更新、浏览器资源清理（shutdown 超时与 terminate
顺序）、管理员权限、只读工具过滤、联网触发、系统 Chrome 路径。发布流程：commit → push main → 打 tag（如 `v1.3.3`）→ release.yml 自动
打包发布（zip 已排除 `dist/`、`.github/`、`data/`、`__pycache__`）。

## 🤝 致谢

- 上游项目：[cmdst/astrbot_plugin_browser_llm](https://github.com/cmdst/astrbot_plugin_browser_llm)
- 灵感与部分交互模式参考 [astrbot_plugin_browser](https://github.com/Zhalslar/astrbot_plugin_browser)（Playwright 浏览器操作思路）
- llm_tool / 会话过滤模式参考 AstrBot 生态插件与 [AstrBot 官方文档](https://astrbot.app/)
- 多模态识图链路基于 AstrBot 的多模态 Provider 能力

## 📄 许可证

[MIT](./LICENSE)
