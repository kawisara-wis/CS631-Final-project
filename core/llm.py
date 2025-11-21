# core/llm.py
import os
import time
from typing import Optional

# ---------- ENV ----------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5")  # เช่น gpt-5 หรือ gpt-5-thinking หรือ o3-mini ฯลฯ
LLM_API = os.getenv("LLM_API", "responses").lower()  # "responses" | "chat"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# การตั้งค่าทั่วไป
DEFAULT_TEMP = float(os.getenv("LLM_TEMPERATURE", "0.2"))
DEFAULT_MAXTOK = int(os.getenv("LLM_MAX_TOKENS", "512"))
RETRIES = int(os.getenv("LLM_RETRIES", "3"))
RETRY_SLP = float(os.getenv("LLM_RETRY_SLEEP", "0.8"))

_openai_client = None


def _ensure_openai():
    """
    lazy init OpenAI client (sdk v1 style)
    """
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set in environment (.env)")

    try:
        # openai>=1.x style
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
        return _openai_client
    except Exception as e:
        raise RuntimeError(f"OpenAI SDK import/init failed: {e}")


def _call_openai_responses(
    prompt: str,
    system: Optional[str] = None,
    max_tokens: int = DEFAULT_MAXTOK,
    temperature: float = DEFAULT_TEMP,  # ไม่ได้ใช้จริง แค่ให้ signature ตรง
    json_mode: bool = False,           # ไม่ได้ใช้จริงใน responses
) -> str:
    """
    เรียกผ่าน Responses API (เหมาะกับ gpt-5*, o-series ฯลฯ)

    ⚠️ สำคัญ:
    - โมเดล reasoning บางตัว (เช่น o3-mini) **ไม่รองรับ temperature** บน Responses API
      เราเลย *ไม่ส่ง* พารามิเตอร์ temperature ไป
    - json_mode จะไม่ถูกใช้ในฟังก์ชันนี้ (ถ้าอยากได้ JSON ให้ไปใช้ Chat API)
    """
    client = _ensure_openai()

    # รวม system + user เป็น text เดียวแบบง่าย ๆ
    user_text = prompt
    if system:
        user_text = f"[SYSTEM]\n{system}\n[/SYSTEM]\n\n[USER]\n{prompt}\n[/USER]"

    # ห้ามใส่ temperature / response_format ตรงนี้
    resp = client.responses.create(
        model=LLM_MODEL,
        input=user_text,
        max_output_tokens=int(max_tokens),
    )

    # พยายามดึง text ออกแบบปลอดภัย
    text = getattr(resp, "output_text", None)
    if text is None:
        # fallback combine
        try:
            parts = []
            for item in getattr(resp, "output", []) or []:
                if hasattr(item, "content"):
                    for c in item.content or []:
                        if getattr(c, "type", "") == "output_text":
                            parts.append(getattr(c, "text", "") or "")
            text = "".join(parts)
        except Exception:
            text = str(resp)
    return text.strip()


def _call_openai_chat(
    prompt: str,
    system: Optional[str] = None,
    max_tokens: int = DEFAULT_MAXTOK,
    temperature: float = DEFAULT_TEMP,
    json_mode: bool = False,
) -> str:
    """
    เรียกผ่าน Chat Completions API (รองรับ temperature + JSON mode)
    """
    client = _ensure_openai()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": int(max_tokens),
    }

    # ส่วนใหญ่ chat models รองรับ temperature
    kwargs["temperature"] = temperature

    if json_mode:
        # JSON mode: ใช้ได้บน chat API รุ่นใหม่ ๆ
        kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


def call_llm(
    prompt: str,
    system: Optional[str] = None,
    max_tokens: int = DEFAULT_MAXTOK,
    temperature: float = DEFAULT_TEMP,
    json_mode: bool = False,
) -> str:
    """
    ฟังก์ชันรวม เรียก LLM พร้อม retry

    นโยบาย:
    - ถ้า json_mode=True → บังคับใช้ Chat API (เพราะต้องการ response_format)
    - ถ้า json_mode=False → ใช้ LLM_API จาก env:
        - responses → ใช้ Responses API (ไม่ส่ง temperature)
        - chat      → ใช้ Chat API (ส่ง temperature ได้)
    """
    if LLM_PROVIDER != "openai":
        raise RuntimeError(f"Unsupported LLM_PROVIDER={LLM_PROVIDER} (only 'openai' supported in this file).")

    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            # กรณีขอ JSON → ไป chat เสมอ
            if json_mode:
                return _call_openai_chat(
                    prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    json_mode=True,
                )

            # ปกติ: เลือกตาม LLM_API
            if LLM_API == "responses":
                return _call_openai_responses(
                    prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    json_mode=False,
                )
            elif LLM_API == "chat":
                return _call_openai_chat(
                    prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    json_mode=False,
                )
            else:
                # fallback: responses
                return _call_openai_responses(
                    prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    json_mode=False,
                )

        except Exception as e:
            last_err = e
            msg = str(e)

            # auto-switch แบบอ่อน ๆ ถ้าชนเรื่องพารามิเตอร์
            if "max_output_tokens" in msg and attempt == 1 and LLM_API == "responses":
                os.environ["LLM_API"] = "chat"
                globals()["LLM_API"] = "chat"
                time.sleep(RETRY_SLP)
                continue

            if "max_tokens" in msg and attempt == 1 and LLM_API == "chat":
                os.environ["LLM_API"] = "responses"
                globals()["LLM_API"] = "responses"
                time.sleep(RETRY_SLP)
                continue

            if attempt < RETRIES:
                time.sleep(RETRY_SLP)
            else:
                raise RuntimeError(f"call_llm failed after {RETRIES} retries: {e}") from e

    # safety net
    raise RuntimeError(f"call_llm failed: {last_err}")
