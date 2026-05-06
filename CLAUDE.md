# 拾句 (Poetry App) — CLAUDE.md

## 项目概述

个人诗词管理工具，主要供自己使用。核心价值：解决"用截图保存诗词、查找繁琐"的痛点。
设计时预留多用户和数据采集扩展能力。

## 三大功能模块

### 1. 诗词库
- 智能录入：输入标题或任意一句残句，语义匹配 corpus 自动识别，补全作者、朝代、词牌名、全文，用户确认后保存
- 搜索与筛选：按词牌名 / 作者 / 朝代筛选
- 背诵追踪：标记"已背会"，按词牌名查看背诵进度

### 2. 配诗日记
- 上传照片 → Gemini Flash 识别场景 → 语义检索匹配诗词 → 用户选择 → 存入当日日记
- 日历视图浏览历史日记

### 3. 推荐（后期）
- 基于收藏风格推荐相似诗词

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 后端 | Python + FastAPI | |
| ORM | SQLAlchemy | 方便后期从 SQLite 迁移到 PostgreSQL |
| 数据库 | SQLite（当前）→ PostgreSQL（扩展） | 改一行连接字符串即可迁移 |
| 前端 | HTML + Tailwind CSS + 原生 JS | 响应式，手机/电脑均适配 |
| 向量库 | ChromaDB（本地） | |
| Embedding | sentence-transformers（本地，免费） | |
| 视觉模型 | Gemini Flash API | 免费额度充足 |
| 文字生成 | DeepSeek API | 便宜，中文强 |

## 数据模型

```
Poem: id, title, author, dynasty, ci_pai, content, is_memorized, created_at
DiaryEntry: id, date, photo_path, scene_description, poem_id, note, created_at
UserLog: id, action, query, result_poem_id, created_at   ← 用于数据采集/后期分析
```

## 目录结构

```
poetry-app/
├── CLAUDE.md
├── .env                 ← API keys（不入 git）
├── requirements.txt
├── data/
│   ├── corpus/          ← chinese-poetry 公开数据集
│   └── personal/        ← 用户录入的诗词
├── vectorstore/         ← Chroma 向量库（自动生成，不入 git）
├── backend/
│   ├── main.py          ← FastAPI 入口
│   ├── db.py            ← SQLAlchemy 配置
│   ├── models.py        ← 数据模型定义
│   ├── routes/
│   │   ├── poems.py     ← 诗词库增删改查
│   │   ├── search.py    ← 语义搜索/智能录入
│   │   └── diary.py     ← 配诗日记
│   └── services/
│       ├── embedder.py  ← sentence-transformers
│       ├── vision.py    ← Gemini 看图
│       └── llm.py       ← DeepSeek 生成
└── frontend/
    ├── index.html
    └── static/
        ├── css/
        └── js/
```

## RAG 核心链路

```
输入残句 → sentence-transformers 向量化 → Chroma 检索 corpus → 返回候选 → 用户确认 → 存入个人库
拍照 → Gemini 提取场景描述 → sentence-transformers 向量化 → Chroma 检索 → 匹配诗词 → 存入日记
```

## 扩展方向（后期）

- SQLite → PostgreSQL：改连接字符串，其他代码不动
- 加用户系统：多人使用，采集行为数据
- UserLog 数据用途：训练更好的匹配模型、改进推荐、用户行为分析

## 开发原则

- 先跑通功能，不过度设计
- 每完成一个功能模块做一次 git commit
- API key 只写在 .env，绝不提交
