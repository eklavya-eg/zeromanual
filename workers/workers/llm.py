import os
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class StructuredLLM:
    def __init__(self, provider: str, model: str) -> None:
        self.model = model
        if provider == "openai":
            self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        elif provider == "openrouter":
            self.client = OpenAI(
                api_key=os.environ["OPENROUTER_API_KEY"],
                base_url="https://openrouter.ai/api/v1",
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def generate(self, *, system_prompt: str, prompt: str, schema: type[T]) -> T:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            },
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned an empty structured response")
        return schema.model_validate_json(content)
