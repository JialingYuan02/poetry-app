import os
import io
from PIL import Image
from google import genai
from google.genai import types


POETRY_PROMPT = """请分析这张照片，提取适合配中国古典诗词的关键信息，严格按以下格式输出（每项一行）：

意境：（2-3个词，例如：清幽寂寥、壮阔豪迈、温柔婉约）
意象：（3-6个核心意象，例如：月、江水、落叶、西风、孤舟）
季节时间：（例如：深秋黄昏、春日午后、冬夜）
诗风：（从以下选一个：婉约、豪放、山水田园、边塞、咏物、思乡、离别、闲适）
检索词：（5-8个适合搜索古诗的关键词，空格分隔，用古典意象词汇）

只输出以上五行，不要其他解释。"""


class VisionService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY 未设置")
        self.client = genai.Client(api_key=api_key)
        self._initialized = True

    def analyze_for_poetry(self, image_bytes: bytes) -> dict:
        """返回结构化意境分析，专为古诗检索设计。"""
        # 缩小图片再发给 Gemini：意境分析不需要原图分辨率，节省 2-5 秒上传时间
        MAX_DIM = 1024
        try:
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode != "RGB":
                img = img.convert("RGB")
            if img.width > MAX_DIM or img.height > MAX_DIM:
                img.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82)
            jpeg_bytes = buf.getvalue()
        except Exception as e:
            return {"error": f"图片处理失败：{e}"}

        for attempt in range(2):          # 遇到限速时自动重试一次
            try:
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
                        POETRY_PROMPT,
                    ],
                )
                return _parse_poetry_analysis(response.text.strip())
            except Exception as e:
                err = str(e).lower()
                if ("quota" in err or "rate" in err or "429" in err) and attempt == 0:
                    import time
                    time.sleep(1.5)
                    continue
                if "not found" in err or "404" in err or "invalid" in err:
                    return {"error": f"Gemini 模型错误：{e}"}
                return {"error": f"图片分析失败：{e}"}
        return {"error": "Gemini API 配额限制，请稍后重试"}

    def build_search_text(self, analysis: dict, user_text: str = "") -> str:
        """合并 Gemini 分析 + 用户文字为检索字符串，用户文字权重翻倍。"""
        parts = []
        if analysis.get("search_keywords"):
            parts.append(analysis["search_keywords"])
        if analysis.get("imagery"):
            parts.append(analysis["imagery"])
        if analysis.get("mood"):
            parts.append(analysis["mood"])
        if analysis.get("season"):
            parts.append(analysis["season"])
        if user_text.strip():
            parts.append(user_text.strip())
            parts.append(user_text.strip())
        return " ".join(parts)


def _parse_poetry_analysis(text: str) -> dict:
    result = {
        "mood": "",
        "imagery": "",
        "season": "",
        "style": "",
        "search_keywords": "",
        "raw": text,
    }
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("意境："):
            result["mood"] = line[3:].strip()
        elif line.startswith("意象："):
            result["imagery"] = line[3:].strip()
        elif line.startswith("季节时间："):
            result["season"] = line[5:].strip()
        elif line.startswith("诗风："):
            result["style"] = line[3:].strip()
        elif line.startswith("检索词："):
            result["search_keywords"] = line[4:].strip()
    return result
