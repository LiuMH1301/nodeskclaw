---
name: media-generator
description: Image and video generation tools via DALL-E 3 and Runway Gen-3
---

# Media Generator

You have access to image and video generation tools powered by external APIs.

## Available Tools

| Tool | Provider | Cost | Description |
|------|----------|------|-------------|
| generate_image | DALL-E 3 | ~$0.04 | Generate an image from a text prompt |
| edit_image | DALL-E 3 | ~$0.04 | Edit an existing image with instructions |
| describe_image | GPT-4o | ~$0.005 | Analyze an image and describe it |
| generate_video | Runway Gen-3 | ~$0.50 | Generate a short video from a prompt |

## Cost Budgets (server-enforced)

API calls have hard budget limits enforced server-side. These cannot be bypassed.

| Tool | Max per hour | Max cost/hour |
|------|-------------|---------------|
| generate_image | 25 | ~$1.00 |
| edit_image | 25 | ~$1.00 |
| describe_image | 100 | ~$0.50 |
| generate_video | 5 | ~$2.50 |

If you receive a `budget_exceeded` error, wait for the budget window to reset.

## Workflow

1. **Plan** -- Decide what media you need based on the content strategy
2. **Generate** -- Create images or video with descriptive prompts
3. **Review** -- Use `describe_image` to self-critique generated images
4. **Iterate** -- Regenerate or edit if quality is insufficient
5. **Save** -- Generated media is auto-saved to the media directory

## Image Generation Tips

- Be specific in prompts: include style, mood, composition, colors
- Use `1792x1024` for landscape/hero images, `1024x1792` for portrait/stories
- Use `style: "natural"` for photorealistic, `style: "vivid"` for artistic

## Video Generation

- ALWAYS confirm cost with the user before generating video
- Use a reference image when possible for better results
- 5s videos are cheaper and faster; use 10s only when needed
- Video generation takes 1-5 minutes -- inform the user of the wait

## What NOT to Do

- Never generate video without confirming cost with the user first
- Never generate more than 10 images in a single batch without user approval
- Never fabricate that an image was generated -- if generation fails, report the error
- Never use describe_image as a substitute for actually reading text in an image
- Never ignore budget_exceeded errors -- they protect against cost overruns
