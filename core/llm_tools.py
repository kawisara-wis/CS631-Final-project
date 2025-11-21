# core/llm_tools.py
import json
from core.llm import CLIENT, MODEL

def run_chat_with_tools(messages, tools, tool_choice="auto", response_format=None):
    # ใช้ Chat Completions + tool calling / structured outputs
    kwargs = {"model": MODEL, "messages": messages, "tools": tools, "tool_choice": tool_choice}
    if response_format:  # บังคับ JSON schema ได้
        kwargs["response_format"] = response_format
    resp = CLIENT.chat.completions.create(**kwargs)
    return resp
