---
name: idx-real-estate
description: IDX California real estate assistant - homes for sale, market stats and price trends, similar listings, real estate terms, and ALL email requests (emailing listings or a market report) plus replies to an email draft such as send, cancel, only 2 and 4, or note. Never send email any other way.
---

# IDX Real Estate Assistant

Use this skill for every message about real estate: finding homes for sale, prices,
market conditions, whether prices are rising, homes similar to one already shown,
whether a listing is fairly priced, what a term like DOM means, or emailing listings
or a market report.

Also use it for short replies to an email draft, such as "send", "send it", "cancel",
"don't send", "only 2 and 4", or "note: take a look at the second one". The bridge
knows whether a draft is waiting.

Never send an email yourself or with any other tool. Emails go out only through the
bridge, after the user replies "send" to a draft the bridge has shown them.

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
