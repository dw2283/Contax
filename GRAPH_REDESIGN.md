# Graph 视图重设计需求

## 背景

当前图谱是 person-centric：人物节点在中间，公司节点在上方，兴趣 topic 节点在下方，固定 grid 布局排列。

**目标：改成 tag-centric 的图谱**，让用户能以 tag（公司、兴趣）为切入点探索人脉网络。

---

## 核心交互层级

```
[全局视图] Tag 气泡图
     ↓ 点击 tag 节点
[中级视图] Tag 展开 → 右侧 panel 列出该 tag 下的所有人
     ↓ 点击某个人
[详情视图] 右侧 panel 切换为 PersonCard，显示该人所有 tag/feature
```

---

## 节点设计

### Tag 节点（主节点）
- 节点代表每一个 tag（包括 company 和 interest/topic 两种类型）
- **节点大小** = 该 tag 下的人数（人越多，气泡越大）
- 颜色区分保留：company = 紫色 (#8b6fd6)，topic = 绿色 (#4ba373)
- 节点内显示：tag 名称 + 人数角标

### Tag 之间的边（新增）
- 两个 tag 共同出现在同一个人身上，则在两者之间连一条边
- **边的粗细** = 共现人数（共享人越多，线越粗）
- 这样可以直观看出哪些 tag 经常共现

---

## 布局引擎

**从固定 grid 改为 force-directed 布局**

- 推荐用 `react-force-graph` 或 `@xyflow/react` + `d3-force` 插件
- force 布局让共享 tag 多的人自然聚拢，cluster 自然涌现
- 不需要手动计算 `x: 300 + column * 250` 这样的固定位置

---

## 右侧 Panel 行为（替代 inline 展开）

**重要：点击节点时，图的布局不重排**，只在右侧 panel 更新内容。

- 点击 **tag 节点** → panel 显示该 tag 下的人员列表（头像/名字/role/公司）
- 点击 **某个人** → panel 切换为 PersonCard，显示该人全部 tag 和 feature
- 点击空白处 → panel 关闭，回到全局 tag 视图

---

## Zoom 级别的 LOD（Level of Detail）

根据当前 zoom 值，节点显示不同详细程度：

| zoom 值 | 显示内容 |
|---------|---------|
| < 0.5   | 只显示 tag 名 + 气泡大小 |
| 0.5–1.0 | tag 名 + 人数 + tag 间连线 |
| > 1.0   | 展示更多细节（可选：hover 时 preview 人员） |

可以通过 `useViewport()` hook 获取当前 zoom 值来条件渲染。

---

## 数据来源（无需改后端）

现有 `Person` 类型已有：
- `company: string` → 作为 company tag
- `interests: string[]` → 作为 topic tags

Tag 节点和共现边的逻辑全部在前端 `graph.ts` 里计算即可。

---

## 需要修改的文件

| 文件 | 修改内容 |
|------|---------|
| `app/lib/graph.ts` | 重写 `graphFromPeople`：改为输出 tag 节点 + tag 间共现边，去掉 person 作为主节点 |
| `app/components/GraphNodes.tsx` | 更新 TagNode 组件，支持可变大小气泡 |
| `app/components/GraphCanvas.tsx` | 接入 force 布局，添加 zoom LOD 逻辑，侧边 panel 状态管理 |
| `app/page.tsx` | panel 状态提升：`selectedTag` + `selectedPerson` 两层状态 |

---

## 不需要改的

- 后端 API（`/api/ingest`、`/api/match`）
- `Person` 类型定义
- CopilotSidebar 及 `findPeople` action
- Toolbar 上传/ingest 流程
