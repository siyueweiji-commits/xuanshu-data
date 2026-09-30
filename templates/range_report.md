# 玄枢 · 流日区间参考

**区间**：{{dateFrom}} ~ {{dateTo}}（共 {{days}} 天）
**档案**：{{profileName}}
**生成时间**：{{generatedAt}}

## 区间概览

共 {{days}} 天，累计命中注意事项 {{totalAdvice}} 条。

| 分类 | 条数 | 占比 |
| --- | --- | --- |
| 事业 | {{nCareer}} | {{pCareer}} |
| 财运 | {{nWealth}} | {{pWealth}} |
| 人际 | {{nPeople}} | {{pPeople}} |
| 健康 | {{nHealth}} | {{pHealth}} |
| 出行 | {{nTravel}} | {{pTravel}} |

## 重点日

{{#keyDays}}
- **{{date}}（{{weekCn}}）** {{reason}}
{{/keyDays}}
{{^keyDays}}
- 区间内没有需要特别留意的日期，整体平稳。
{{/keyDays}}

## 逐日摘要

| 日期 | 星期 | 日柱 | 建除 | 星宿 | 条数 | 首要提示 |
| --- | --- | --- | --- | --- | --- | --- |
{{#dailyRows}}
| {{date}} | {{weekCn}} | {{dayGanZhi}} | {{zhiXing}} | {{xiu}} | {{count}} | {{top}} |
{{/dailyRows}}

## 高频提示

{{#adviceTop}}
- **【{{group}}】** {{text}}（命中 {{count}} 天）
{{/adviceTop}}
{{^adviceTop}}
- 区间内没有重复出现的提示。
{{/adviceTop}}

## 分类要点

{{#groupSummary}}
### {{group}}（{{count}} 条）

{{#items}}
- **{{date}}**：{{text}}
{{/items}}

{{/groupSummary}}
{{^groupSummary}}
- 暂无分类提示。
{{/groupSummary}}

## 说明

本报告由「玄枢」根据内置规则库自动拼接生成，区间内每一条提示都来自规则库中已启用的规则。
规则库为 JSON 文本，可在「设置 · 规则库」中查看、启用或禁用，修改后立即生效。

---

> ⚠️ 本报告为文化娱乐工具输出，仅供个人自省参考，
> 不构成任何医疗、法律、投资或驾驶安全建议，不承诺任何预测准确性。
