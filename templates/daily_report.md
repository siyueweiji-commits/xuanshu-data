# 玄枢 · 流日参考

**日期**：{{dateCn}}（农历 {{lunarDate}}）
**档案**：{{profileName}}
**干支**：{{yearGanZhi}}年 {{monthGanZhi}}月 {{dayGanZhi}}日　**纳音**：{{naYin}}　**日柱五行**：{{wuXing}}
**生成时间**：{{generatedAt}}

## 黄历参考

| 项目 | 内容 |
| --- | --- |
| 宜 | {{yi}} |
| 忌 | {{ji}} |
| 冲煞 | {{chongSha}} |
| 建除十二神 | {{zhiXing}}日 |
| 二十八宿 | {{xiu}}（{{xiuLuck}}） |
| 值日天神 | {{tianShen}}（{{tianShenType}}{{tianShenLuck}}） |
| 节气 | {{jieQi}} |
| 吉时 | {{jiShi}}（共 {{luckyHourCount}} 个） |
| 财神 / 喜神方位 | {{caiFang}} / {{xiFang}} |
| 彭祖百忌 | {{pengZu}} |
| 吉神 | {{jiShen}} |
| 凶煞 | {{xiongSha}} |

## 今日注意事项

{{#advice}}
- **【{{group}}】** {{text}}　*({{source}})*
{{/advice}}
{{^advice}}
- 今日未命中任何规则，按平常节奏行事即可。
{{/advice}}

## 分类速览

{{#groupSummary}}
### {{group}}（{{count}} 条）

{{#items}}
- {{text}}
{{/items}}

{{/groupSummary}}
{{^groupSummary}}
- 暂无分类提示。
{{/groupSummary}}

## 命盘要点

{{#hasBirth}}
- **本人生肖**：{{shengXiao}}{{clashNote}}
- **八字**：日主 {{dayMaster}}（{{dayMasterWuXing}}）· {{baziLevel}} · 生于{{season}}季
- **喜用五行**：{{favorable}}　**忌神**：{{unfavorable}}{{#hasMissing}}　**缺五行**：{{missing}}{{/hasMissing}}
- **流日命宫**：落本命{{landedPalace}}，主星 {{soulStars}}
- **流日四化**：禄 {{mutagenLu}} ／ 权 {{mutagenQuan}} ／ 科 {{mutagenKe}} ／ 忌 {{mutagenJi}}

{{#starNotes}}
- **{{name}}**（{{wuxing}}）：{{brief}}
{{/starNotes}}
{{/hasBirth}}
{{^hasBirth}}
- 未叠加个人命盘，本节略去。如需个性化提示，请填写生辰后重新生成。
{{/hasBirth}}

## 说明

本报告由「玄枢」根据内置规则库自动拼接生成。规则库为 JSON 文本，可在「设置 · 规则库」中查看、
启用或禁用，修改后立即生效。所有条目均属传统文化内容，不构成事实判断。

---

> ⚠️ 本报告为文化娱乐工具输出，仅供个人自省参考，
> 不构成任何医疗、法律、投资或驾驶安全建议，不承诺任何预测准确性。
