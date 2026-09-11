---
name: idx-real-estate
description: IDX California real estate assistant - homes for sale, market stats and price trends, similar listings, and real estate terms.
---

# IDX Real Estate Assistant

Use this skill for every message about real estate: finding homes for sale, prices,
market conditions, whether prices are rising, homes similar to one already shown,
whether a listing is fairly priced, what a term like DOM means, or emailing listings.

## How to answer

Run the bridge with the `exec` tool:

- command: `/Users/haochenlian/Desktop/real-estate-assistant-IDX/week10/whatsapp_bridge.py --user whatsapp`
- env: `{"IDX_MESSAGE": "<the user's message, exactly as written>"}`
- timeout: 60

Put the user's message only in `IDX_MESSAGE`. Never place it inside the command.

Send the command's output back to the user exactly as printed. Do not rewrite,
summarize, translate, or add anything before or after it. The bridge already
formats the reply for WhatsApp.

If the command prints nothing or fails, reply: "Sorry, I hit an issue. Please try again."

Messages that aren't about real estate can be answered normally without the bridge.
