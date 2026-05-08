# 拾句 (Poetry App) — CLAUDE.md

## 产品定位

**一句话：为你眼前的景，配三首恰好的诗。**

用户拍一张照片，可选输入心情/关键词，AI 分析图片意境并推荐 2-3 首既切题又有流传度的古诗词。
面向个人使用，后期可分享。

## 核心流程

```
上传照片
    ↓
Gemini Flash 分析图片 → 提取意境关键词（意境/意象/季节/诗风）
    ↓
合并 Gemini 描述 + 用户补充文字（用户文字权重 ×2）
    ↓
sentence-transformers 向量化 → ChromaDB 语义搜索
    ↓
相似度 × 作者名气加成 × 诗长度加成，过滤冷门无名氏
    ↓
返回 2-3 首：主题相关 + 有流传度
```

## 功能清单

### MVP（当前目标）
- 照片上传（支持相机拍摄/相册选择）
- Gemini Flash 意境分析（专门为古诗检索设计的 prompt）
- 用户补充文字（可选，提升匹配精度）
- 推荐 2-3 首诗词（可滑动卡片展示）
- 展示全文 + 作者 + 朝代 + 词牌名

### 后期可加
- 历史记录（查看过去的配诗）
- 分享卡片（照片 + 诗词合成图）
- 多模式：只输文字不拍照

## 配诗质量策略（最核心）

### Gemini Prompt 设计
不做通用场景描述，专门提取古诗检索关键词：
- 意境（2-3词：清幽/壮阔/惆怅）
- 核心意象（月/江水/落叶/西风）
- 季节/时间（深秋/黄昏/春夜）
- 诗风倾向（婉约/豪放/山水/边塞）

### 排序算法
```
最终分数 = 向量相似度 × 作者名气系数 × 诗长度系数

作者名气系数：李白/杜甫=1.30，苏轼=1.25，辛弃疾=1.22，...（见 search.py）
诗长度系数：≤40字=1.10，41-100字=1.0，>100字=0.9（短诗流传度更高）
冷门过滤：无名氏诗词相似度阈值提高到 0.18（普通诗词 0.12）
```

### 用户文字权重
用户输入的文字与 Gemini 描述合并时，用户文字复制一遍（相当于权重 ×2），
因为用户意图比 AI 猜测更准确。

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 后端 | Python + FastAPI | |
| ORM | SQLAlchemy | 一行改连接串可迁移 PostgreSQL |
| 数据库 | SQLite | data/personal/poetry.db |
| 前端 | HTML + Tailwind CSS + 原生 JS | 手机优先，无构建步骤 |
| 向量库 | ChromaDB（本地持久化） | vectorstore/ 目录 |
| Embedding | BAAI/bge-small-zh-v1.5（本地） | BGE 检索前缀：为这个句子生成表示以用于检索相关文章 |
| 视觉 | Gemini Flash API（免费） | 图片意境分析 |

**不使用 DeepSeek**（原用于元数据补全，新方向不需要）。

## 数据模型

```
Poem
  id, title, author, dynasty, ci_pai, content
  source: "corpus"（公共语料库）
  created_at

MatchRecord（可选，记录历史）
  id, photo_path, gemini_description, user_text
  poem_ids: JSON 数组（推荐的 2-3 首）
  created_at

UserLog
  id, action, query, result_poem_id, created_at
```

注：`is_memorized` 字段在数据库中存在但不再使用。

## 目录结构

```
poetry-app/
├── CLAUDE.md
├── .env                    ← GEMINI_API_KEY, DATABASE_URL
├── requirements.txt
├── data/
│   ├── corpus/             ← chinese-poetry 公开数据集（已导入）
│   ├── personal/           ← 上传的照片存放处
│   └── ingest_corpus.py    ← 一次性导入脚本（已运行）
├── vectorstore/            ← ChromaDB 向量库（已生成，不入 git）
├── backend/
│   ├── main.py             ← FastAPI 入口 + CORS + 静态文件
│   ├── db.py               ← SQLAlchemy engine/session
│   ├── models.py           ← Poem, UserLog（已有）
│   ├── routes/
│   │   ├── match.py        ← 核心：图片+文字 → 推荐诗词（待开发）
│   │   └── search.py       ← 语义搜索工具函数（已有，可复用）
│   └── services/
│       ├── embedder.py     ← BGE 向量化 + ChromaDB（已有）
│       └── vision.py       ← Gemini Flash 看图（框架已有，待接 key）
└── frontend/
    ├── index.html          ← 单页，手机优先（待重新设计）
    └── static/
        ├── css/custom.css
        └── js/app.js
```

## 当前开发状态

### 已完成 ✅
- 语料库导入：39万首诗词进 SQLite + ChromaDB
- 向量检索：BGE 模型，余弦相似度，搜索正常
- 作者名气排序：FAMOUS_POETS 权重表
- 词牌名/诗名精确匹配逻辑
- 图片上传接口（backend/routes/diary.py）
- Gemini vision.py 代码框架

### 待开发 🔧
1. **Gemini API 接入**（需要用户提供 key）
   - 修改 vision.py 的 prompt 为古诗关键词提取
2. **新建 /match 接口**（match.py）
   - 合并图片描述 + 用户文字
   - 调用搜索，返回 2-3 首
   - 加入诗长度系数和冷门过滤
3. **前端重新设计**
   - 去掉三Tab，改为单页配诗体验
   - 卡片滑动展示 2-3 首推荐

## 开发原则

- 先跑通配诗质量，再打磨 UI
- 每完成一个可测试的功能做一次 git commit
- API key 只写在 .env，绝不提交
- 配诗质量是核心，宁可多迭代 prompt 也不要堆功能
