
import os
import base64
import mimetypes
from pathlib import Path
from typing import Literal
from pydantic import BaseModel
from openai import OpenAI


class LLM:
    def __init__(
        self,
        model_provider: Literal["openai", "openrouter"],
        model_name: str,
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.model_name = model_name
        self.model_provider = model_provider
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens

        if model_provider == "openai":
            self.client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY")
            )
        elif model_provider == "openrouter":
            self.client = OpenAI(
                api_key=os.getenv("OPENROUTER_API_KEY"),
                base_url="https://openrouter.ai/api/v1"
            )
        else:
            raise ValueError("Unsupported model provider")

    def _encode_file(self, path: str):
        path = Path(path)
        mime_type, _ = mimetypes.guess_type(path)

        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        return encoded, mime_type or "application/octet-stream"

    def generate_text(
        self,
        prompt: str,
        images: list[str] | None = None,
        files: list[str] | None = None,
        output_schema: type[BaseModel] | None = None
    ) -> str:

        schema = output_schema.model_json_schema()

        content = [
            {
                "type": "text",
                "text": prompt
            }
        ]

        for image_path in images or []:
            encoded, mime_type = self._encode_file(image_path)

            if not mime_type.startswith("image/"):
                raise ValueError(f"Not an image: {image_path}")

            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{encoded}"
                }
            })

        for file_path in files or []:
            path = Path(file_path)
            encoded, mime_type = self._encode_file(file_path)

            if mime_type == "application/pdf":
                content.append({
                    "type": "file",
                    "file": {
                        "filename": path.name,
                        "file_data": f"data:{mime_type};base64,{encoded}"
                    }
                })
            elif mime_type.startswith("text/") or path.suffix.lower() in {
                ".json", ".md", ".py", ".csv"
            }:
                content.append({
                    "type": "text",
                    "text": f"\n\nFile: {path.name}\n{path.read_text(encoding='utf-8')}"
                })
            else:
                raise ValueError(f"Unsupported file type: {mime_type}")

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "system",
                    "content": self.system_prompt
                },
                {
                    "role": "user",
                    "content": content
                }
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": output_schema.__name__,
                    "strict": True,
                    "schema": schema
                }
            } if output_schema else None
        )

        content = response.choices[0].message.content

        try:
            return output_schema.model_validate_json(content)

        except Exception as e:
            return None
            return content
            # logger.info(f"Response does not match schema: {content}")
    