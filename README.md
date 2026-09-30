# xuanshu-data

[玄枢 XuanShu](https://github.com/siyueweiji-commits/xuanshu) 的**在线更新源**（静态文件仓库，无需服务器）。

应用通过 GitHub Raw 拉取 `manifest.json`，比对本地版本后下载差异文件，校验 sha256 后写入用户数据目录（不覆盖安装目录，失败回滚）。

## 目录结构

```
xuanshu-data/
├─ rules/          # 规则库（ziwei / bazi / meihua / liuyao / huangli）
├─ knowledge/      # 知识库（星曜释义等）
├─ templates/      # 报告模板
├─ data/           # 城市经纬度等基础数据
└─ manifest.json   # 版本清单 + 文件哈希
```

## manifest 格式

```json
{
  "version": "2026.09.30",
  "files": [
    { "path": "rules/ziwei.json", "hash": "sha256:..." }
  ]
}
```

## 发布更新

1. 修改 `rules/` / `knowledge/` / `templates/` / `data/` 下的文件
2. 重新生成 manifest：`python scripts/gen_manifest.py`
3. 提交推送即可，客户端下次检查更新时自动拉取

## 免责声明

本仓库中的规则与知识内容仅供文化娱乐与个人自省参考，不构成任何医疗、法律、投资或安全建议。
