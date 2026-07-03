"""
Interfaccia comune per i provider LLM (Groq, Gemini, ...).

Tutti i provider espongono lo stesso formato di input/output, così il resto
dell'applicazione (orchestratore, tool, view) non deve sapere quale provider
è effettivamente in uso: per cambiarlo basta modificare LLM_PROVIDER nel .env.

Formato messaggi (stile "OpenAI-like", il più diffuso e facile da convertire
verso qualunque provider):
    {"role": "user" | "assistant" | "tool", "content": "...", ...}

Formato tool definition (JSON Schema, stile Anthropic/OpenAI function calling):
    {
        "name": "nome_funzione",
        "description": "...",
        "parameters": {"type": "object", "properties": {...}, "required": [...]}
    }

Risposta del modello (LLMResponse):
    - content: testo della risposta (può essere vuoto se il modello ha solo
      richiesto l'uso di un tool)
    - tool_calls: lista di chiamate a funzione richieste dal modello, ognuna
      con id, name, arguments (dict già parsato)
"""
from dataclasses import dataclass, field
from typing import Any


class LLMError(Exception):
    """
    Errore generico di comunicazione con il provider LLM (rate limit/quota
    esaurita, richiesta rifiutata, timeout, errore di rete, ...). Ogni client
    concreto traduce qui le proprie eccezioni specifiche dell'SDK, così
    l'orchestratore può gestire un errore del provider senza sapere quale
    provider è effettivamente in uso né i dettagli della sua libreria.
    """
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None  # risposta grezza del provider, utile per debug/log

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMClient:
    """Interfaccia che ogni provider LLM deve implementare."""

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str = "",
    ) -> LLMResponse:
        """
        Invia una conversazione al modello con la lista di tool disponibili.

        messages: lista di messaggi nel formato neutro descritto sopra.
        tools: lista di tool definition nel formato neutro descritto sopra.
        system_prompt: istruzioni di sistema per il modello.

        Ritorna un LLMResponse con il testo generato e/o le tool call richieste.
        """
        raise NotImplementedError

    def format_tool_result_message(self, tool_call: ToolCall, result: Any) -> dict:
        """
        Costruisce il messaggio da accodare alla conversazione dopo aver
        eseguito un tool, nel formato richiesto dal provider specifico.
        """
        raise NotImplementedError

    def format_assistant_tool_call_message(self, response: LLMResponse) -> dict:
        """
        Costruisce il messaggio 'assistant' da accodare alla conversazione
        quando il modello ha richiesto una o più tool call, prima di
        accodare i risultati dei tool stessi (richiesto dal formato a
        history di entrambi i provider).
        """
        raise NotImplementedError
