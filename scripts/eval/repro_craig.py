import os, json
from pathlib import Path
from ingest.voicenote_loader import load_obsidian_voicenote
from pharoah.classifier.classifier import _envelope_tool_schema
from pharoah.classifier.prompts import (
    SYSTEM_PROMPT, render_user_message, CLASSIFIER_MODEL_PRIMARY)
from shared.clients.anthropic import AnthropicClient

p = '/home/benjaminbot/wiki/voicenotes/2026-05-14 Dr. Craig Wing POV draft reviewed, contract with Craig urgent priority.md'
s = load_obsidian_voicenote(p)
print(f'transcript_len: {len(s.transcript)}')

c = AnthropicClient()
user_msg = render_user_message(s.source_id, s.source_type.value,
    s.captured_at.isoformat(), s.transcript, s.title_hint,
    s.metadata.get("duration_seconds"))
print(f'user_msg len: {len(user_msg)}')

import anthropic
client = anthropic.Anthropic()
tool = {"name": "produce_envelope",
        "description": "Produce a classified Envelope.",
        "input_schema": _envelope_tool_schema()}
print('calling Anthropic with full Craig transcript...')
resp = client.messages.create(
    model=CLASSIFIER_MODEL_PRIMARY, max_tokens=4096, temperature=0,
    system=SYSTEM_PROMPT, tools=[tool],
    tool_choice={"type": "tool", "name": "produce_envelope"},
    messages=[{"role": "user", "content": user_msg}],
)
print(f'stop_reason: {resp.stop_reason}')
print(f'usage: in={resp.usage.input_tokens} out={resp.usage.output_tokens}')
for i, block in enumerate(resp.content):
    print(f'block {i}: type={getattr(block, "type", "?")}')
    if hasattr(block, "input"):
        print(f'  input keys: {list(block.input.keys())}')
        if "items" in block.input:
            print(f'  n items: {len(block.input["items"])}')
        else:
            print(f'  RAW: {json.dumps(block.input)[:500]}')
