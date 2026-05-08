import json
import os
from openai import OpenAI


class LLMService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
        self._initialized = True

    def enrich_poem_metadata(self, content: str) -> dict:
        prompt = (
            f"以下是一首诗词的内容：\n\n{content}\n\n"
            "请返回 JSON，包含字段：title（标题）、author（作者）、dynasty（朝代）、ci_pai（词牌名，不是词则为空字符串）。"
            "只返回 JSON，不要其他内容。"
        )
        resp = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        text = resp.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)

    def generate_poem_note(self, poem_content: str, scene_description: str) -> str:
        prompt = (
            f"场景描述：{scene_description}\n\n"
            f"诗词内容：{poem_content}\n\n"
            "请用2-3句话写一段将这首诗词与该场景结合的鉴赏文字，语言优美，古典风格。只返回鉴赏文字。"
        )
        resp = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()
