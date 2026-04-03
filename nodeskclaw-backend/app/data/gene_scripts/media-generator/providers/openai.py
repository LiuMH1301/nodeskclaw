"""
OpenAI provider module: DALL-E 3 image generation + GPT-4o Vision description.

To add a new provider, copy this file's structure:
1. Export PROVIDER dict with: name, allowed_domains, env_keys, tools, cost_limits
2. Export async handle(tool_name, args, ctx) function
3. Place in providers/<name>.py
4. Add tool names to gene manifest's tool_allow
That's it -- server.py auto-discovers this file.
"""

from __future__ import annotations

import base64
import os

import httpx
from mcp.types import Tool


PROVIDER = {
    "name": "openai",
    "allowed_domains": [
        "api.openai.com",
        "oaidalleapiprodscus.blob.core.windows.net",
    ],
    "env_keys": ["OPENAI_API_KEY", "OPENAI_BASE_URL"],
    "tools": [
        Tool(
            name="generate_image",
            description="Generate an image from a text prompt using DALL-E 3. Cost: ~$0.04 per image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Image generation prompt."},
                    "size": {
                        "type": "string",
                        "enum": ["1024x1024", "1792x1024", "1024x1792"],
                        "default": "1024x1024",
                    },
                    "style": {
                        "type": "string",
                        "enum": ["natural", "vivid"],
                        "default": "vivid",
                    },
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="edit_image",
            description="Edit an existing image with a text instruction. Cost: ~$0.04 per edit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "URL or local path of the image to edit."},
                    "prompt": {"type": "string", "description": "Edit instruction."},
                },
                "required": ["image_url", "prompt"],
            },
        ),
        Tool(
            name="describe_image",
            description="Analyze an image and return a text description using GPT-4o Vision. Cost: ~$0.005.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "URL or local path of the image."},
                },
                "required": ["image_url"],
            },
        ),
    ],
    "cost_limits": {
        "generate_image": {"cost_per_call": 0.04, "max_per_hour": 25},
        "edit_image": {"cost_per_call": 0.04, "max_per_hour": 25},
        "describe_image": {"cost_per_call": 0.005, "max_per_hour": 100},
    },
}


def _api_key() -> str:
    """Read API key at call time (supports rotation without restart)."""
    return os.environ.get("OPENAI_API_KEY", "")


MAX_PROMPT_LENGTH = 4000
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB


def _base_url(ctx) -> str:
    """Read and validate base URL at call time. Prevents env-var-based API key theft."""
    url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    ctx.validate_base_url(url)
    return url


def _safe_client(timeout: int = 60) -> httpx.AsyncClient:
    """Create httpx client with security defaults: no redirect following."""
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False)


async def _read_image_bytes(url: str, ctx) -> bytes:
    """Read image bytes from validated URL or local path. Max 20MB."""
    ctx.url_validator.require_valid_url(url)

    if url.startswith("/"):
        from pathlib import Path
        data = Path(url).read_bytes()
        if len(data) > MAX_IMAGE_SIZE:
            raise ValueError(f"Image exceeds {MAX_IMAGE_SIZE // (1024*1024)}MB limit.")
        return data

    async with _safe_client(timeout=60) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        if len(resp.content) > MAX_IMAGE_SIZE:
            raise ValueError(f"Image exceeds {MAX_IMAGE_SIZE // (1024*1024)}MB limit.")
        content_type = resp.headers.get("content-type", "")
        if content_type and not content_type.startswith("image/"):
            raise ValueError(f"Expected image content, got {content_type}.")
        return resp.content


async def handle(tool_name: str, args: dict, ctx) -> dict:
    """Dispatch OpenAI tool calls."""
    api_key = _api_key()
    if not api_key:
        return {"error": "OPENAI_API_KEY not configured"}

    if tool_name == "generate_image":
        return await _generate_image(api_key, args, ctx)
    elif tool_name == "edit_image":
        return await _edit_image(api_key, args, ctx)
    elif tool_name == "describe_image":
        return await _describe_image(api_key, args, ctx)
    else:
        return {"error": "unknown_tool", "tool": tool_name}


async def _generate_image(api_key: str, args: dict, ctx) -> dict:
    prompt = args["prompt"]
    if not prompt or len(prompt) > MAX_PROMPT_LENGTH:
        return {"error": "invalid_input", "message": f"Prompt must be 1-{MAX_PROMPT_LENGTH} characters."}

    size = args.get("size", "1024x1024")
    style = args.get("style", "vivid")
    base = _base_url(ctx)

    async with _safe_client(timeout=120) as client:
        resp = await client.post(
            f"{base}/images/generations",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": size,
                "style": style,
                "response_format": "b64_json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    image_data = data["data"][0]
    image_bytes = base64.b64decode(image_data["b64_json"])

    save_path = ctx.save_path("png")
    save_path.write_bytes(image_bytes)

    return {
        "local_path": str(save_path),
        "revised_prompt": image_data.get("revised_prompt", prompt),
        "size": size,
    }


async def _edit_image(api_key: str, args: dict, ctx) -> dict:
    image_url = args["image_url"]
    prompt = args["prompt"]
    if not prompt or len(prompt) > MAX_PROMPT_LENGTH:
        return {"error": "invalid_input", "message": f"Prompt must be 1-{MAX_PROMPT_LENGTH} characters."}

    img_bytes = await _read_image_bytes(image_url, ctx)
    base = _base_url(ctx)

    async with _safe_client(timeout=120) as client:
        resp = await client.post(
            f"{base}/images/edits",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"image": ("image.png", img_bytes, "image/png")},
            data={"prompt": prompt, "n": "1", "size": "1024x1024", "response_format": "b64_json"},
        )
        resp.raise_for_status()
        data = resp.json()

    image_bytes = base64.b64decode(data["data"][0]["b64_json"])
    save_path = ctx.save_path("png")
    save_path.write_bytes(image_bytes)

    return {"local_path": str(save_path), "prompt": prompt}


async def _describe_image(api_key: str, args: dict, ctx) -> dict:
    image_url = args["image_url"]
    ctx.url_validator.require_valid_url(image_url)

    content = [
        {"type": "text", "text": "Describe this image in detail. Focus on composition, mood, colors, and subject matter."},
    ]
    if image_url.startswith("/"):
        from pathlib import Path
        img_bytes = Path(image_url).read_bytes()
        if len(img_bytes) > MAX_IMAGE_SIZE:
            return {"error": "invalid_input", "message": f"Image exceeds {MAX_IMAGE_SIZE // (1024*1024)}MB limit."}
        encoded = base64.b64encode(img_bytes).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}})
    else:
        content.append({"type": "image_url", "image_url": {"url": image_url}})

    base = _base_url(ctx)

    async with _safe_client(timeout=60) as client:
        resp = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 500,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    return {"description": data["choices"][0]["message"]["content"]}
