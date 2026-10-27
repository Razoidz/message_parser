# Chat Analysis

A learning project that analyzes chat conversations and suggests each
person's role and how events unfolded, with every claim linked to the
messages that support or contradict it.

## How it works
1. Parse a WhatsApp export into messages
2. Store messages in SQLite
3. Split into overlapping chunks and extract events and actions with an LLM
4. Synthesize roles, a timeline and a narrative
5. Validate: drop any claim that cites a message that doesn't exist
6. View results in a Flask web page, with evidence under each claim

## Status
Prototype. The pipeline is tested with fake model replies. The real
model call (Anthropic API) is implemented but not yet evaluated on real chats.

## Important
Findings are what the messages suggest, not verdicts. Chats are
incomplete, and the model can be wrong. Only analyze chats you have
the right to use, and keep a human reviewing the results.