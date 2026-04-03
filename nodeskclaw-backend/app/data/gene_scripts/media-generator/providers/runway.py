"""
Runway Gen-3 provider module: video generation from text/image prompts.

Same provider module contract as openai.py. See that file for the pattern.
"""

from __future__ import annotations

import asyncio
import os

import httpx
from mcp.types import Tool

MAX_PROMPT_LENGTH = 2000
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB
MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100MB

PROVIDER = {
    "name": "runway",
    "allowed_domains": [
        "api.dev.runwayml.com",
        "runwayml.com",
    ],
    "env_keys": ["RUNWAY_API_KEY"],
    "tools": [
        Tool(
            name="generate_video",
            description="Generate a short video from a text prompt using Runway Gen-3. Cost: ~$0.50 per 5s video. IMPORTANT: Confirm cost with user before generating.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Video generation prompt."},
                    "duration": {
                        "type": "string",
                        "enum": ["5s", "10s"],
                        "default": "5s",
                    },
                    "reference_image_url": {
                        "type": "string",
                        "description": "Optional reference image URL or local path.",
                    },
                },
                "required": ["prompt"],
            },
        ),
    ],
    "cost_limits": {
        "generate_video": {"cost_per_call": 0.50, "max_per_hour": 5},
    },
}

API_BASE = "https://api.dev.runwayml.com/v1"
POLL_INTERVAL = 5  # seconds
MAX_POLL_ITERATIONS = 60  # 5 minutes total


def _api_key() -> str:
    return os.environ.get("RUNWAY_API_KEY", "")


def _safe_client(timeout: int = 60) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False)


def _safe_raise(resp: httpx.Response) -> None:
    """Raise on HTTP errors without leaking Authorization headers or API keys."""
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"API returned {e.response.status_code}: {e.response.text[:200]}"
        ) from None


async def handle(tool_name: str, args: dict, ctx) -> dict:
    """Dispatch Runway tool calls."""
    api_key = _api_key()
    if not api_key:
        return {"error": "RUNWAY_API_KEY not configured"}

    if tool_name == "generate_video":
        return await _generate_video(api_key, args, ctx)
    else:
        return {"error": "unknown_tool", "tool": tool_name}


async def _generate_video(api_key: str, args: dict, ctx) -> dict:
    prompt = args["prompt"]
    if not prompt or len(prompt) > MAX_PROMPT_LENGTH:
        return {"error": "invalid_input", "message": f"Prompt must be 1-{MAX_PROMPT_LENGTH} characters."}

    duration = args.get("duration", "5s")
    duration_seconds = 10 if duration == "10s" else 5

    # Build request payload
    payload = {
        "promptText": prompt,
        "model": "gen3a_turbo",
        "duration": duration_seconds,
    }

    # Optional reference image
    ref_url = args.get("reference_image_url")
    if ref_url:
        ctx.url_validator.require_valid_url(ref_url)
        # If local path, read and would need to upload -- for now, only support URL refs
        if ref_url.startswith("/"):
            return {"error": "unsupported", "message": "Local reference images are not yet supported for video generation. Provide an HTTPS URL instead."}
        payload["promptImage"] = ref_url

    # Submit generation task
    async with _safe_client(timeout=30) as client:
        resp = await client.post(
            f"{API_BASE}/image_to_video",
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Runway-Version": "2024-11-06",
            },
            json=payload,
        )
        _safe_raise(resp)
        task = resp.json()

    task_id = task.get("id")
    if not task_id:
        return {"error": "api_error", "message": "No task ID returned from Runway API."}

    # Poll for completion
    for _ in range(MAX_POLL_ITERATIONS):
        await asyncio.sleep(POLL_INTERVAL)

        async with _safe_client(timeout=30) as client:
            resp = await client.get(
                f"{API_BASE}/tasks/{task_id}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "X-Runway-Version": "2024-11-06",
                },
            )
            _safe_raise(resp)
            status = resp.json()

        state = status.get("status", "")
        if state == "SUCCEEDED":
            output_url = (status.get("output", []) or [""])[0]
            if not output_url:
                return {"error": "api_error", "message": "Video generated but no output URL returned."}

            # Validate output URL before downloading (SSRF protection)
            ctx.url_validator.require_valid_url(output_url)

            # Download video with streaming size check
            async with _safe_client(timeout=120) as client:
                downloaded = bytearray()
                async with client.stream("GET", output_url) as video_resp:
                    _safe_raise(video_resp)
                    async for chunk in video_resp.aiter_bytes():
                        downloaded.extend(chunk)
                        if len(downloaded) > MAX_VIDEO_SIZE:
                            raise ValueError(f"Video exceeds {MAX_VIDEO_SIZE // (1024*1024)}MB limit.")

            save_path = ctx.save_path("mp4")
            save_path.write_bytes(bytes(downloaded))

            return {
                "local_path": str(save_path),
                "duration": duration,
                "task_id": task_id,
                "prompt": prompt,
            }

        if state == "FAILED":
            failure = status.get("failure", "Unknown failure")
            return {"error": "generation_failed", "message": str(failure)[:200], "task_id": task_id}

    return {"error": "timeout", "message": f"Video generation timed out after {MAX_POLL_ITERATIONS * POLL_INTERVAL}s.", "task_id": task_id}
