"""
Implementazione LLMClient per Google AI Studio / Gemini.

Gemini usa un formato diverso da OpenAI/Groq per i ruoli ("model" invece di
"assistant", nessun ruolo "tool" — i risultati dei tool sono "function
response" parts dentro un messaggio "user"). La conversione avviene tutta
qui dentro, così il resto dell'app non se ne accorge.
"""
import json
from google import genai
from google.genai import types

from .base import LLMClient, LLMResponse, ToolCall


DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def _to_gemini_tools(self, tools: list[dict]) -> list[types.Tool]:
        declarations = [
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=tool["parameters"],
            )
            for tool in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    def _to_gemini_contents(self, messages: list[dict]) -> list[types.Content]:
        """
        Converte i messaggi dal formato neutro (stile OpenAI) al formato
        Content/Part richiesto da Gemini.
        """
        contents = []
        for msg in messages:
            role = msg["role"]

            if role == "user":
                contents.append(types.Content(role="user", parts=[types.Part(text=msg["content"])]))

            elif role == "assistant":
                parts = []
                if msg.get("content"):
                    parts.append(types.Part(text=msg["content"]))
                for tc in msg.get("tool_calls", []):
                    parts.append(types.Part(function_call=types.FunctionCall(
                        name=tc["name"], args=tc["arguments"],
                    )))
                contents.append(types.Content(role="model", parts=parts))

            elif role == "tool":
                # Gemini si aspetta il risultato del tool come "function_response"
                # in un messaggio con role="user" (non esiste un ruolo "tool" dedicato).
                contents.append(types.Content(role="user", parts=[types.Part(
                    function_response=types.FunctionResponse(
                        name=msg["name"],
                        response={"result": msg["content"]},
                    )
                )]))

        return contents

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str = "",
    ) -> LLMResponse:
        contents = self._to_gemini_contents(messages)

        config_kwargs = {"temperature": 0.3}
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt
        if tools:
            config_kwargs["tools"] = self._to_gemini_tools(tools)

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        text_parts = []
        tool_calls = []
        candidate = response.candidates[0] if response.candidates else None

        if candidate and candidate.content and candidate.content.parts:
            for i, part in enumerate(candidate.content.parts):
                if part.text:
                    text_parts.append(part.text)
                if part.function_call:
                    # Gemini non fornisce un ID univoco per le tool call: lo
                    # generiamo noi (indice + nome) per coerenza con l'interfaccia.
                    tool_calls.append(ToolCall(
                        id=f"call_{i}_{part.function_call.name}",
                        name=part.function_call.name,
                        arguments=dict(part.function_call.args or {}),
                    ))

        return LLMResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            raw=response,
        )

    def format_tool_result_message(self, tool_call: ToolCall, result) -> dict:
        # Manteniamo 'name' nel messaggio neutro: serve a _to_gemini_contents
        # per costruire correttamente la FunctionResponse.
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.name,
            "content": json.dumps(result, default=str, ensure_ascii=False),
        }

    def format_assistant_tool_call_message(self, response: LLMResponse) -> dict:
        return {
            "role": "assistant",
            "content": response.content or "",
            "tool_calls": [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in response.tool_calls
            ],
        }
