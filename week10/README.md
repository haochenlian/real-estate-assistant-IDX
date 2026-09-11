# Week 10 — WhatsApp Communication Layer

## In one sentence

This connects the Week 9 orchestrator to **WhatsApp**, so users search for homes, ask about
the market, and get recommendations from their phone, with replies formatted for a chat app.

## What problem it solves

After Week 9 the assistant had one entry point, `orchestrate()`, but it only ran in a
terminal. Week 10 gives it a real conversational interface. WhatsApp is also where the
capstone is demoed, so everything built so far has to work end to end through it.

## How it works (no code needed)

```
WhatsApp message
    ↓
OpenClaw agent (receives the message; the idx-real-estate skill tells it what to do)
    ↓ runs whatsapp_bridge.py
load this user's saved session → orchestrate() → agents → MySQL
    ↓
format the reply for WhatsApp, save the session
    ↓
the agent sends the reply back unchanged
    ↓
WhatsApp
```

1. **OpenClaw receives the message.** Its WhatsApp channel only accepts messages from
   numbers on an allowlist; anyone else is ignored.
2. **The skill routes it to the bridge.** `SKILL.md` tells the OpenClaw agent to run
   `whatsapp_bridge.py` for any real estate question and to send back exactly what it prints.
3. **The bridge calls the orchestrator.** Week 9 classifies the message and runs the right
   agent (property search, market stats, recommendations, knowledge Q&A, or email drafting).
4. **The bridge formats the reply** with WhatsApp's `*bold*` and `_italic_`, one card per home.
5. **The agent sends it back.** The typing indicator the handbook asks for comes from
   OpenClaw itself: by default it shows "typing…" in direct chats while the agent works.

## What a reply looks like

A search, followed by *"Show me homes similar to the first one"* in a second message:

```
✨ *Homes similar to 300 N El Molino #312* ($378,000)

🏠 *972 E California 307, Pasadena*
💰 $399,000 | 🛏 0bd/1ba | 📐 555 sqft
📅 24 days on market | ⭐ match 60/60

💡 *Price check:* priced below comparable sales. 7 similar-sized sales suggest about $487,800 (-22.5%).
```

| Agent | WhatsApp formatting |
|-------|--------------------|
| Property search | Header, then a card per home (🏠 address, 💰 price, 🛏 beds/baths, 📐 sqft, 📅 days on market) |
| Market stats | The answer first (📈 rising / ➖ roughly flat / 📉 falling, per sqft), the monthly price per sqft behind it and the date the data ends, then 📊 one bullet per metric |
| Recommendations | ✨ header naming the home they liked, cards with ⭐ match score, 💡 price check |
| Knowledge Q&A | The answer, then an italic *Sources* line |
| Email, follow-up questions, errors | Sent as plain text |

## Remembering the conversation

The skill starts a **new Python process for every message**. Week 4 keeps sessions (city,
budget, last search results) in memory, so on its own the assistant would forget everything
between messages, and *"show me similar homes"* would answer "search for homes first".

The bridge fixes this by **saving each user's session to a JSON file** after every reply and
loading it before the next message:

- Files live in `~/.idx-assistant/sessions/`, outside the repo, because they hold the sender's
  id and search history. Set `IDX_SESSION_DIR` to use another folder.
- Files are readable only by the Mac user who runs OpenClaw (`600`, folder `700`).
- Each save writes a temporary file and then swaps it in, so a crash mid-write can't leave a
  half-written session.
- Missing or corrupt files start a fresh session instead of failing. Fields from an older
  version are ignored.

## Safety

- **The message never goes into the shell command.** The skill passes it in the
  `IDX_MESSAGE` environment variable, so text like `"; rm -rf ~` stays a message instead of
  becoming a command.
- **Only allowlisted numbers get answers.** OpenClaw's `dmPolicy: "allowlist"` drops messages
  from anyone not on `channels.whatsapp.allowFrom`. The phone numbers live in OpenClaw's local
  config, not in this repo.
- **Any failure becomes an apology.** If the database is down or anything throws, the user gets
  *"Sorry, I hit an issue. Please try again."* instead of silence or a stack trace.
- **Session file names are sanitized**, so a user id can never point outside the session folder.

## The files in this folder

| File | What it is |
|------|------------|
| `whatsapp_bridge.py` | Runs once per message: loads the session, calls `orchestrate()`, formats the reply for WhatsApp, saves the session. |
| `test_whatsapp_bridge.py` | 20 tests: formatting for every agent, session save/restore across processes, private file permissions, failure paths, and the command line. |
| `skill/idx-real-estate/SKILL.md` | The OpenClaw skill that tells the agent when to run the bridge and to forward its output unchanged. |
| `README.md` | This explanation. |

## How to run it

```bash
# Tests (should print 20/20 passed) — no WhatsApp, database, or API key needed
python3 test_whatsapp_bridge.py

# Answer one message from the terminal, exactly as OpenClaw does
# (needs MySQL running and OPENAI_API_KEY in .env; makes one classification call)
IDX_MESSAGE="Are prices rising in Pasadena?" ./whatsapp_bridge.py --user test
```

### Connecting it to WhatsApp

```bash
# 1. Install the skill for the OpenClaw agent, then check it shows as ready
mkdir -p ~/.openclaw/workspace/skills/idx-real-estate
cp skill/idx-real-estate/SKILL.md ~/.openclaw/workspace/skills/idx-real-estate/
openclaw skills list

# 2. Link WhatsApp (scan the QR code in WhatsApp > Settings > Linked Devices)
openclaw channels login --channel whatsapp

# 3. Allow only your own numbers, then restart so it takes effect
openclaw config set channels.whatsapp.allowFrom '["+1XXXXXXXXXX"]' --strict-json
openclaw gateway restart

# 4. Confirm it's connected
openclaw channels status
```

`SKILL.md` and the first line of `whatsapp_bridge.py` contain this machine's paths (the repo
location and `/opt/anaconda3/bin/python3`). Update both on another machine: the OpenClaw
service doesn't use your terminal's `PATH`, and the system Python has no `openai` package.

## Live test results

Tested over WhatsApp against the real database and OpenAI:

| Message | Routed to | Result |
|---------|-----------|--------|
| *Are prices rising in Pasadena?* | market | Market card with trend (tested before the trend switched to price per sqft) |
| *Find me affordable homes in Pasadena and tell me whether prices are rising.* | mixed | 5 home cards + market card in one reply |
| *Show me homes similar to the first one.* (new message, sent from a second number) | recommend | 3 similar homes + price check, using the search saved from the previous message |

The mixed request took about **16 seconds** from message to reply: about 6 seconds for the
OpenClaw agent to decide to run the skill, about 5 seconds for the bridge (classification plus
two database agents in parallel), and about 5 seconds to send the reply. The agent's output
matched the bridge's output character for character.

## Known gaps

- **Two models sit in the chain.** The OpenClaw agent decides whether to run the skill, then
  the orchestrator classifies the message. In testing the agent always ran the bridge and
  forwarded its output unchanged, but that relies on it following `SKILL.md`. An OpenClaw
  plugin that claims inbound messages before the agent runs would remove that layer and about
  10 seconds of latency.
- **The knowledge index is rebuilt for every knowledge question.** Week 9 builds it once per
  process, but each WhatsApp message is a new process, so every *"What does DOM mean?"*
  re-embeds all 15 passages. Saving the index to a file would fix this.
- **All allowlisted numbers share one session.** The skill passes the fixed id `whatsapp`
  because it doesn't receive the sender's number. That's fine for one person using two
  numbers; several users would need the sender id passed through.
- **It runs on a personal WhatsApp number.** The OpenClaw agent is a linked device on the
  owner's own account; OpenClaw recommends a dedicated number. To keep the owner's messages and
  the agent's replies on opposite sides of the chat, the owner messages the agent from a second
  allowlisted number. WhatsApp logs linked devices out if the phone is offline for a long time
  (this happened after about two months unused), which requires scanning the QR code again.
- **The OpenClaw agent may run any shell command.** The skill uses the `exec` tool, which is
  unrestricted in the current OpenClaw policy. A shared deployment should allowlist only
  `whatsapp_bridge.py`.

## Where this fits

```
Week 9: one entry point for every agent   →   Week 10: reachable from WhatsApp   →   Week 11: email with human approval
```

Week 10 turns the assistant from something you run in a terminal into something you text.
