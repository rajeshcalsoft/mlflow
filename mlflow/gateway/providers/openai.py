from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from .base import BaseProvider
from .utils import send_request, rename_payload_keys
from ..schemas import chat, completions, embeddings
from ..config import OpenAIConfig, RouteConfig


class OpenAIProvider(BaseProvider):
    def __init__(self, config: RouteConfig) -> None:
        super().__init__(config)
        if config.model.config is None or not isinstance(config.model.config, OpenAIConfig):
            # Should be unreachable
            raise TypeError(f"Invalid config type {config.model.config}")
        self.openai_config: OpenAIConfig = config.model.config
        self.headers = {"Authorization": f"Bearer {self.openai_config.openai_api_key}"}
        if org := self.openai_config.openai_organization:
            self.headers["OpenAI-Organization"] = org
        self.base_url = self.openai_config.openai_api_base

    async def chat(self, payload: chat.RequestPayload) -> chat.ResponsePayload:
        payload = jsonable_encoder(payload, exclude_none=True)
        if "n" in payload:
            raise HTTPException(
                status_code=400, detail="Invalid parameter `n`. Use `candidate_count` instead."
            )

        payload = rename_payload_keys(
            payload,
            {"candidate_count": "n"},
        )
        # The range of OpenAI's temperature is 0-2, but ours is 0-1, so we double it.
        payload["temperature"] = 2 * payload["temperature"]

        resp = await send_request(
            headers=self.headers,
            base_url=self.base_url,
            path="chat/completions",
            payload={"model": self.config.model.name, **payload},
        )
        # Response example (https://platform.openai.com/docs/api-reference/chat/create)
        # ```
        # {
        #    "id":"chatcmpl-abc123",
        #    "object":"chat.completion",
        #    "created":1677858242,
        #    "model":"gpt-3.5-turbo-0301",
        #    "usage":{
        #       "prompt_tokens":13,
        #       "completion_tokens":7,
        #       "total_tokens":20
        #    },
        #    "choices":[
        #       {
        #          "message":{
        #             "role":"assistant",
        #             "content":"\n\nThis is a test!"
        #          },
        #          "finish_reason":"stop",
        #          "index":0
        #       }
        #    ]
        # }
        # ```
        return chat.ResponsePayload(
            **{
                "candidates": [
                    {
                        "message": {
                            "role": c["message"]["role"],
                            "content": c["message"]["content"],
                        },
                        "metadata": {
                            "finish_reason": c["finish_reason"],
                        },
                    }
                    for c in resp["choices"]
                ],
                "metadata": {
                    "input_tokens": resp["usage"]["prompt_tokens"],
                    "output_tokens": resp["usage"]["completion_tokens"],
                    "total_tokens": resp["usage"]["total_tokens"],
                    "model": resp["model"],
                    "route_type": self.config.route_type,
                },
            }
        )

    async def completions(self, payload: completions.RequestPayload) -> completions.ResponsePayload:
        payload = jsonable_encoder(payload, exclude_none=True)
        if "n" in payload:
            raise HTTPException(
                status_code=400, detail="Invalid parameter `n`. Use `candidate_count` instead."
            )
        payload = rename_payload_keys(
            payload,
            {"candidate_count": "n"},
        )
        # The range of OpenAI's temperature is 0-2, but ours is 0-1, so we double it.
        payload["temperature"] = 2 * payload["temperature"]
        payload["messages"] = [{"role": "user", "content": payload.pop("prompt")}]
        resp = await send_request(
            headers=self.headers,
            base_url=self.base_url,
            path="chat/completions",
            payload={"model": self.config.model.name, **payload},
        )
        # Response example (https://platform.openai.com/docs/api-reference/completions/create)
        # ```
        # {
        #   "id": "cmpl-uqkvlQyYK7bGYrRHQ0eXlWi7",
        #   "object": "text_completion",
        #   "created": 1589478378,
        #   "model": "text-davinci-003",
        #   "choices": [
        #     {
        #       "text": "\n\nThis is indeed a test",
        #       "index": 0,
        #       "logprobs": null,
        #       "finish_reason": "length"
        #     }
        #   ],
        #   "usage": {
        #     "prompt_tokens": 5,
        #     "completion_tokens": 7,
        #     "total_tokens": 12
        #   }
        # }
        # ```
        return completions.ResponsePayload(
            **{
                "candidates": [
                    {
                        "text": c["message"]["content"],
                        "metadata": {"finish_reason": c["finish_reason"]},
                    }
                    for c in resp["choices"]
                ],
                "metadata": {
                    "input_tokens": resp["usage"]["prompt_tokens"],
                    "output_tokens": resp["usage"]["completion_tokens"],
                    "total_tokens": resp["usage"]["total_tokens"],
                    "model": resp["model"],
                    "route_type": self.config.route_type,
                },
            }
        )

    async def embeddings(self, payload: embeddings.RequestPayload) -> embeddings.ResponsePayload:
        payload = rename_payload_keys(
            jsonable_encoder(payload, exclude_none=True),
            {"text": "input"},
        )
        resp = await send_request(
            headers=self.headers,
            base_url=self.base_url,
            path="embeddings",
            payload={"model": self.config.model.name, **payload},
        )
        # Response example (https://platform.openai.com/docs/api-reference/embeddings/create):
        # ```
        # {
        #   "object": "list",
        #   "data": [
        #     {
        #       "object": "embedding",
        #       "embedding": [
        #         0.0023064255,
        #         -0.009327292,
        #         .... (1536 floats total for ada-002)
        #         -0.0028842222,
        #       ],
        #       "index": 0
        #     }
        #   ],
        #   "model": "text-embedding-ada-002",
        #   "usage": {
        #     "prompt_tokens": 8,
        #     "total_tokens": 8
        #   }
        # }
        # ```
        return embeddings.ResponsePayload(
            **{
                "embeddings": [d["embedding"] for d in resp["data"]],
                "metadata": {
                    "input_tokens": resp["usage"]["prompt_tokens"],
                    "output_tokens": 0,  # output_tokens is not available for embeddings
                    "total_tokens": resp["usage"]["total_tokens"],
                    "model": resp["model"],
                    "route_type": self.config.route_type,
                },
            }
        )