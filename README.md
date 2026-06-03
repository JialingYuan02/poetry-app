<div align="center">

# 拾 句

### 为你眼前的景，配三首恰好的诗

拍一张照片，AI 分析画面意境，从 38 万首古诗词中为你挑出最贴合的那几句。

**[→ 立即体验 shiju.app](https://shiju.app)**

</div>

---

## 界面预览

<table>
  <tr>
    <td align="center"><b>主页</b></td>
    <td align="center"><b>上传配诗</b></td>
    <td align="center"><b>配诗结果</b></td>
    <td align="center"><b>日历</b></td>
    <td align="center"><b>记录详情</b></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/home.jpg" width="180"/></td>
    <td><img src="docs/screenshots/add.jpg" width="180"/></td>
    <td><img src="docs/screenshots/matching.jpg" width="180"/></td>
    <td><img src="docs/screenshots/calendar.jpg" width="180"/></td>
    <td><img src="docs/screenshots/detail.jpg" width="180"/></td>
  </tr>
</table>

<div align="center">
  <img src="docs/screenshots/list.jpg" width="440"/>
  <p><i>诗词日记列表 — 每张照片都有属于它的那句诗</i></p>
</div>

---

## 功能介绍

### 拍照配诗
上传任意一张照片，可选附上当下心情或关键词。AI 同步分析照片意境与用户文字，返回 2–3 首风格、意象最贴合的古诗词，可左右滑动比较，选定后收入日记。

### 语义匹配，而非关键词搜索
底层使用 BGE 中文向量模型对全库诗词编码，搜索时按语义相似度而非字面匹配，能理解「落日余晖」和「夕阳西沉」说的是同一件事。

### 名家权重 + 流传度过滤
李白、杜甫、苏轼等名家诗词获额外加成；无名氏作品须达到更高相似度才能入选，保证推荐结果有品质、有流传度。

### 诗词日历
所有配诗记录按日期存入日历，可月视图浏览，点击任意日期查看当天照片与诗词，支持重新配诗、修改日期、删除。

### 账号与云端同步
注册登录后数据存储在云端，换设备访问记录不丢失。

---

## 配诗流程

```
上传照片
    ↓
Gemini Flash 提取意境关键词
（意境 / 核心意象 / 季节时间 / 诗风倾向）
    ↓
合并 AI 描述 + 用户补充文字（用户文字权重 ×2）
    ↓
BGE 向量化 → ChromaDB 语义搜索 Top 60
    ↓
最终分数 = 相似度 × 名气系数 × 长度系数
过滤低质量 / 冷门无名氏
    ↓
返回 2–3 首
```

**名气系数参考**：李白 / 杜甫 1.30 · 苏轼 1.25 · 辛弃疾 1.22 · 王维 / 白居易 1.20 …

**长度系数**：≤ 40 字（绝句 / 律诗）× 1.06，短诗流传度通常更高

---

## 技术栈

| 层级 | 技术 |
|---|---|
| 后端 | Python · FastAPI |
| 数据库 | PostgreSQL（Railway 托管，38 万首诗永久存储） |
| 向量检索 | ChromaDB · BAAI/bge-small-zh-v1.5 |
| 视觉理解 | Gemini 2.0 Flash |
| 前端 | HTML · Tailwind CSS · 原生 JS，无构建步骤 |
| 图片存储 | Cloudflare R2 |
| 部署 | Railway |

---

## 语料来源

基于 [chinese-poetry](https://github.com/chinese-poetry/chinese-poetry) 开源数据集，收录唐诗、宋词、宋诗、元曲等共约 38.5 万首。
