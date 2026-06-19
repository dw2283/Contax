# Contax — Hackathon TODO

---

## TODO-1：Agent Monitor 界面

**目标**：新增一个独立页面/tab，可视化展示整个 multi-agent 系统的运行状态。

### 需要展示的内容

**Agent 拓扑图**
- 展示项目中设计的所有 Agent（参考 `prm_pipeline.py` 里的 LangGraph 节点）：
  - `orchestrator` → fan-out → `vision_agent`（并行，每张截图一个）
  - `entity_resolution_agent` → 去重合并
  - `embed_agent` → 向量化
  - `storage_agent` → 写入 Redis
  - `matchmaker_agent` → 检索 + 排序
- 用有向图展示 Agent 之间的数据流（输入/输出类型标注在边上）

**Memory 状态面板**
- 显示当前 Redis 里存了多少个 Person
- 向量索引状态（`vector_index_ready: true/false`）
- 每个 Agent 最近一次运行的输出摘要（从 `data_layer.py` 的 `save_agent_output` 读取）

**Traceability 面板 + Agent Timeline 甘特图**
- 集成 Weave trace 链接（现有代码已返回 `weave_call_url`）
- 每次 ingest / match 运行后，显示对应的 Weave trace URL，可点击跳转
- 显示每个 `@weave.op()` 调用的耗时和状态（成功/失败）
- **甘特图**：横轴为时间，每个 Agent 占一行，色块长度 = 实际耗时
  - 数据来源：每个 `@weave.op()` 的 start_time / end_time（从 Weave API 或后端 `/api/status` 返回）
  - 关键视觉：vision_agent 的多行色块并排展示，直观体现 fan-out 并行
  - 底部加"View in Weave →"链接跳转完整 trace
  - 实现方式：SVG 或 D3，不需要引入额外图表库

### 推荐工具（Hackathon stack）
- **Weave**：`weave_call_url` 已在 `/ingest` 和 `/match` 响应里返回，直接用
- **React Flow**：已安装，用来画 Agent 拓扑图
- **数据来源**：后端新增 `GET /api/status` 端点，返回 Redis 状态 + 最近一次各 Agent 的运行记录

### 实现要点
- 路由：在 Next.js 里新增 `/monitor` 页面（`app/monitor/page.tsx`）
- Toolbar 里加一个"Monitor"入口 tab 切换
- 页面定时 poll `GET /api/status`（每 3 秒）刷新状态
- 后端在 `api_server.py` 里加 `/api/status` 端点

---

## TODO-3：跑 anonymized_screenshots 真实截图 pipeline

**目标**：把 `anonymized_screenshots/` 目录下的 8 张真实截图（微信 + LinkedIn）跑一遍完整 ingest pipeline，结果存进 Redis，在图谱里单独展示。

### 截图清单
```
01_whatsapp_business_fake.png
02_whatsapp_business_fake.png
03_wechat_profile_fake.png
04_linkedin_profile_fake.png
05_linkedin_profile_fake.png
06_wechat_profile_fake.png
07_linkedin_profile_fake.png
08_chat_fake.png
```

### 实现步骤

**后端**
1. 在 `api_server.py` 新增 `POST /api/ingest-local`，接收本地文件路径列表（或直接读取 `anonymized_screenshots/` 目录）
2. 把图片 base64 编码后走现有 vision agent 提取 Person 信息
3. source 根据文件名自动判断（`wechat_` → wechat，`linkedin_` → linkedin，`whatsapp_` → whatsapp）

**前端**
1. Toolbar 加"Load Real Screenshots"按钮，调用 `/api/ingest-local`
2. 这批人在图谱里用不同视觉标记区分（比如节点边框加实线，或加"Real"角标），和 demo 数据区分开
3. 在 PersonCard 里显示 `raw_screenshot_ref` 对应的截图缩略图（如果图片可访问）

### 注意
- Vision agent 当前用 deterministic embedding（`deterministic_embedding()`），不依赖 OpenAI，截图文本提取部分需确认是否走真实 LLM 还是规则解析
- 如果 LLM 不可用，fallback：手动从截图文件名推断 source，其余字段填占位符，先跑通流程

---

## TODO-4："Find people like this" 右键快捷操作

**目标**：在图谱上右键点击任意 person 节点，直接以该人的 profile 为 query 触发 match，找出网络里和他最相似的人。

### 交互设计
- 右键 person 节点 → 弹出 context menu，选项：
  - `Find people like this` → 触发 match
  - `Copy name` → 复制姓名到剪贴板
  - `Draft intro` → 生成介绍信（可选，见下）
- match query 构造：把该人的 role + company + interests 拼成自然语言，例如：
  `"ML engineer at Anthropic interested in RLHF and alignment"`
- 结果同现有 match 流程：高亮图上匹配节点 + 右侧 panel 展示推荐列表

### 实现要点
- `GraphCanvas.tsx`：把 `onNodeClick` 改为同时支持 `onNodeContextMenu`
- 弹出菜单用绝对定位 div，点击其他地方关闭
- query 构造逻辑写在 `graph.ts` 里，导出 `personToQuery(person: Person): string`
- 触发的是现有 `runMatch(query)` 函数，无需改后端

### 扩展：Draft Intro 按钮
- PersonCard 里加"Draft Intro"按钮
- 点击后生成两人互相介绍的模板文本，复制到剪贴板
- 模板：`"Hi [A], I'd like to introduce you to [B], [role] at [company]. You both share interest in [common interests]."`

---

## 优先级建议

| TODO | 难度 | 展示价值 | 建议顺序 |
|------|------|---------|---------|
| TODO-4 Find people like this | 低 | 高（交互亮点，demo 友好） | 1st |
| TODO-3 真实截图 | 中 | 高（demo 说服力强） | 2nd |
| TODO-1 Agent Monitor + 甘特图 | 高 | 高（Hackathon 技术亮点） | 3rd |
