# Turn Markdown and AI answers into PNG files in n8n

Browser screenshots work for one answer. They become repetitive when an n8n
workflow needs to turn release notes, code snippets, quotes, or AI-generated
Markdown into image files every day.

This tutorial uses a tested five-node n8n workflow and a small rendering API.
The workflow sends structured Markdown, receives one Dataset record per PNG,
and can hand each runtime `imageUrl` to cloud storage, email, a CMS, or an
owned publishing step. It does not log in to ChatGPT, automate a browser tab,
or scrape another website.

![Example Markdown and code rendered as a PNG](https://raw.githubusercontent.com/Jarvis-Dong/markdown-code-to-image/main/docs/markdown-code-to-image-preview.png)

> **Fastest path for automation:** [open the preconfigured ChatGPT-to-PNG task](https://apify.com/ai-coding-radar/markdown-code-to-image/examples/chatgpt-markdown-answer-to-png). It uses one sample document, requires an Apify account, and shows the current price before you choose whether to run it.

## Import the workflow

Download and import the public n8n workflow:

https://raw.githubusercontent.com/Jarvis-Dong/markdown-code-to-image/main/examples/n8n-markdown-code-to-image.json

It contains five nodes:

1. **Setup notes** explains the credential and output contract.
2. **Run manually** provides a safe trigger for the first test.
3. **Build batch input** creates two Markdown documents.
4. **Render Markdown and code** calls the Actor's synchronous Dataset API.
5. **Return PNG records** passes the generated image records downstream.

The exported JSON contains no API token, credential ID, cookie, private
webhook, or signed output URL.

## Configure authorization without leaking a token

Set `APIFY_TOKEN` in the private environment of your own n8n instance. The HTTP
node reads it at runtime and sends it as a Bearer authorization header. Do not
paste the token into the workflow JSON, a query string, a public repository, or
a screenshot.

The request uses this official endpoint:

```text
POST https://api.apify.com/v2/acts/ai-coding-radar~markdown-code-to-image/run-sync-get-dataset-items?clean=1
Authorization: Bearer <your token from n8n's environment>
Content-Type: application/json
```

For production, replace the manual trigger with a Schedule Trigger, Webhook, or
an event from your CMS. Replace the static input node with Markdown from your
database, changelog generator, or AI step.

## Send a valid batch

A request can contain 1–20 documents. Every item needs non-empty Markdown and
may have a short title:

````json
{
  "documents": [
    {
      "title": "Release note",
      "markdown": "# Shipped\n\nThe useful change is live.\n\n```js\nconst ready = true;\n```"
    },
    {
      "title": "A concise AI answer",
      "markdown": "## Three steps\n\n1. Define the outcome.\n2. Automate repeatable work.\n3. Measure the result."
    }
  ],
  "theme": "paper",
  "width": 1080,
  "fontSize": 22,
  "watermark": ""
}
````

Available themes are `paper`, `midnight`, `terminal`, and `clean`. Width is
limited to 640–1600 pixels, body font size to 16–30 pixels, and each Markdown
value to 12,000 characters. Oversized or malformed input fails instead of
silently producing a partial image.

## Use each returned PNG

The API returns an array. Each successful document has a record containing:

```json
{
  "title": "Release note",
  "theme": "paper",
  "width": 1080,
  "height": 742,
  "format": "png",
  "markdownChars": 78,
  "storageKey": "IMAGE-001.png",
  "imageUrl": "https://runtime-generated-download-url.example",
  "generatedAt": "2026-08-15T08:00:00Z"
}
```

Treat `imageUrl` as a runtime value. Map it directly into an n8n HTTP Request
download, S3-compatible storage, email attachment, or another system you own.
Do not hard-code a previous run's URL; Apify storage retention follows the
caller's plan and settings.

## Start from a focused use case

The ready-to-copy ChatGPT/AI-answer task shows a complete one-image input:

https://apify.com/ai-coding-radar/markdown-code-to-image/examples/chatgpt-markdown-answer-to-png

The public Actor and its general Markdown/code example are here:

https://apify.com/ai-coding-radar/markdown-code-to-image

For a one-off image that does not need an API, Cardify provides a free local
browser editor:

https://cardify.1222155.xyz/chatgpt-to-image/

The browser tool and the Actor have different jobs: use the browser editor for
manual previews, and use the Actor for scheduled, batch, n8n, or Make
automation.

## Rendering and security boundaries

The renderer accepts Markdown, not arbitrary remote web pages. Raw HTML is
disabled, Markdown images are replaced with alt text, and the rendering page
blocks network requests. It does not fetch remote fonts, tracking pixels,
images, Mermaid diagrams, or authenticated pages. These limits prevent input
from turning the renderer into a request proxy.

The current output format is PNG. The generated file uses system fonts, and a
single rendered image is capped at 16,000 pixels high.

## Cost

The public Store page shows the current price before a run. At the time of
writing, the price is `$0.005` per generated image plus `$0.00005` per Actor
start, with platform usage included. Begin with one document and confirm the
displayed cost in your own account before enabling a schedule.

A generated image, free user, page view, or test run is not creator income.
Only a finalized payout that actually settles counts as revenue.
