"""Optional: turn a casual Japanese (or English) description into an English
image-generation prompt, using the Claude API.

Entirely optional. If ANTHROPIC_API_KEY is not set, `is_available()` returns
False and the UI hides the "AIで変換" button - the rest of the site works
exactly the same without it.
"""

import os

import anthropic

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT_POSITIVE = """You are a prompt writer for a Stable Diffusion / Flux image \
generation model used inside ComfyUI, for a visual novel game's character \
portraits and backgrounds.

Turn the user's casual description (it may be in Japanese or English) into a \
single English prompt suitable for txt2img generation.

Rules:
- Output ONLY the prompt itself: no explanation, no quotes, no markdown, no \
  labels like "Prompt:".
- Comma-separated tags and short phrases, in the usual Stable Diffusion style.
- Add concrete visual details the user's request implies but did not spell \
  out: pose, expression, clothing, art style, lighting, composition.
- Keep it under 80 words.
"""

SYSTEM_PROMPT_NEGATIVE = """You are a prompt writer for a Stable Diffusion / Flux image \
generation model used inside ComfyUI, for a visual novel game's character \
portraits and backgrounds.

Turn the user's casual description of things they do NOT want in the image \
(it may be in Japanese or English) into a single English negative prompt \
suitable for txt2img generation.

Rules:
- Output ONLY the negative prompt itself: no explanation, no quotes, no \
  markdown, no labels like "Negative prompt:".
- Comma-separated tags and short phrases, in the usual Stable Diffusion \
  negative-prompt style (e.g. lowres, bad anatomy, extra fingers, watermark).
- Add commonly-paired negative tags implied by the request even if not \
  spelled out (e.g. a complaint about hands should also add "bad hands, \
  extra fingers, fused fingers").
- Keep it under 60 words.
"""


def is_available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def expand_prompt(user_text, kind="positive"):
    """Return an English image-generation prompt for the given casual text.

    `kind` is "positive" (what the image should contain) or "negative"
    (what to avoid) - each uses a differently-tuned system prompt.

    Raises anthropic.AnthropicError (or a subclass) on any API failure -
    callers should catch and show a friendly message.
    """
    system = SYSTEM_PROMPT_NEGATIVE if kind == "negative" else SYSTEM_PROMPT_POSITIVE
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=system,
        messages=[{"role": "user", "content": user_text}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()
