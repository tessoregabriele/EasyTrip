"""
Implementazione LLMClient per Groq (modelli open-source, inferenza velocissima,
tier gratuito senza carta di credito). L'SDK Groq usa un formato API
OpenAI-compatibile, quindi la conversione è diretta.
"""
import json
from groq import Groq

from .base import LLMClient, LLMResponse, ToolCall


# Modello di default: Llama 3.3 70B supporta tool-calling in modo affidabile
# ed è nella fascia di rate-limit "alta" del free tier di Groq.
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqClient(LLMClient):
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.client = Groq(api_key=api_key)
        self.model = model

    def _to_groq_tools(self, tools: list[dict]) -> list[dict]:
        """Converte le tool definition dal formato neutro al formato richiesto da Groq (stile OpenAI)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in tools
        ]

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str = "",
    ) -> LLMResponse:
        groq_messages = []
        if system_prompt:
            groq_messages.append({"role": "system", "content": system_prompt})
        groq_messages.extend(messages)

        kwargs = {
            "model": self.model,
            "messages": groq_messages,
            "temperature": 0.3,  # bassa: vogliamo estrazione/orchestrazione affidabile, non creatività
        }
        if tools:
            kwargs["tools"] = self._to_groq_tools(tools)
            kwargs["tool_choice"] = "auto"

        completion = self.client.chat.completions.create(**kwargs)
        choice = completion.choices[0]
        message = choice.message

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))

        return LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            raw=completion,
        )

    def format_tool_result_message(self, tool_call: ToolCall, result) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result, default=str, ensure_ascii=False),
        }

    def format_assistant_tool_call_message(self, response: LLMResponse) -> dict:
        """
        Costruisce il messaggio 'assistant' da accodare alla conversazione
        quando il modello ha richiesto delle tool call, prima di accodare i
        risultati dei tool. Necessario perché l'API Groq/OpenAI richiede che
        il messaggio assistant con tool_calls sia presente nella history.
        """
        return {
            "role": "assistant",
            "content": response.content or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in response.tool_calls
            ],
        }
