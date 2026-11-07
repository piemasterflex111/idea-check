"""Turn an idea plus the three answers into a verdict, using an AI model.

Works with any OpenAI-compatible chat endpoint: a local model served by
llama.cpp, vLLM or Ollama, or a hosted API.
"""

import json
import os
import re
import urllib.request

VERDICTS = ("Build", "Ask first", "Skip")
FIELDS = ("verdict", "why", "missing_facts", "question_to_send", "done_means", "first_version")

RULES = """You fact-check ideas for tools, scripts, products or services before anyone builds them.
Rules:
- A fact is something someone can check. Mark the person's guesses as guesses. Don't fill gaps with your own assumptions.
- If a tool for this already exists, say so first, in "why".
- Plain words, short, no jargon.

Reply with only a JSON object with these keys:
"verdict": exactly one of "Build", "Ask first", "Skip".
"why": one line on why.
"missing_facts": anything they said that is a guess, and who could tell them the real answer.
"question_to_send": one short, casual message they can send that person to get the missing fact. No lists.
"done_means": what the finished thing does, in one sentence they could check.
"first_version": the smallest piece they can build in one day that shows a real result."""


def build_messages(answers):
    user = (
        f"Idea: {answers['idea']}\n"
        f"1. Who has this problem? {answers['who']}\n"
        f"2. What do they do about it today? {answers['today']}\n"
        f"3. What does it cost them now (time, money or mistakes)? {answers['cost']}"
    )
    return [{"role": "system", "content": RULES}, {"role": "user", "content": user}]


def parse_reply(text):
    """Pull the JSON object out of the model's reply and check it has every field."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("The model did not return JSON.")
    data = json.loads(match.group(0))
    missing = [f for f in FIELDS if not str(data.get(f, "")).strip()]
    if missing:
        raise ValueError(f"The model's reply is missing: {', '.join(missing)}")
    if data["verdict"] not in VERDICTS:
        raise ValueError(f"Unknown verdict: {data['verdict']!r}")
    return {f: str(data[f]).strip() for f in FIELDS}


class OpenAICompatibleModel:
    def __init__(self, base_url=None, model=None, api_key=None, timeout=120):
        self.base_url = (base_url or os.environ.get("IDEA_CHECK_LLM_URL", "http://localhost:8080/v1")).rstrip("/")
        self.model = model or os.environ.get("IDEA_CHECK_LLM_MODEL", "local")
        self.api_key = api_key or os.environ.get("IDEA_CHECK_LLM_KEY", "")
        self.timeout = timeout

    def complete(self, messages):
        body = json.dumps({"model": self.model, "messages": messages, "temperature": 0.2}).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            reply = json.load(resp)
        return reply["choices"][0]["message"]["content"]


def check_idea(answers, model):
    return parse_reply(model.complete(build_messages(answers)))
