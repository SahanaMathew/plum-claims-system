from groq import Groq
from backend.config import GROQ_API_KEY, GROQ_MODEL
import json
import traceback
from datetime import datetime
from backend.models.schemas import TraceStep


class BaseAgent:
    def __init__(self, name: str, model: str = None):
        self.name = name
        self.model = model or GROQ_MODEL
        self.client = Groq(api_key=GROQ_API_KEY)

    def _call_llm(self, system_prompt: str, user_prompt: str, json_mode: bool = True) -> dict:
        """Call Groq LLM with error handling. Returns parsed JSON or error dict."""
        try:
            kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 2048,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            if json_mode:
                return json.loads(content)
            return {"text": content}
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}

    def make_trace_step(
        self,
        status: str,
        input_summary: str = None,
        output_summary: str = None,
        checks: list = None,
        error: str = None,
    ) -> TraceStep:
        return TraceStep(
            agent=self.name,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            checks=checks or [],
            error=error,
            timestamp=datetime.utcnow().isoformat(),
        )

    def run(self, context: dict) -> dict:
        """Override in subclass. Returns updated context dict."""
        raise NotImplementedError
