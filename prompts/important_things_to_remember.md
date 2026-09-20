---
This prompt asks the LLM to extract important working memory items from the conversation.
Used to maintain character autonomy: promises, tasks, emotional state, pending questions.
Based on C++ kuni util/important_things_to_remember.h
---

You just had a conversation. Before you forget, extract the important things you need to remember for next time you talk to this person.

Focus on:
- **Promises you made** — things you said you would do, reminders you agreed to give, tasks you committed to
- **Unfinished tasks** — things you started but didn't complete, topics you need to follow up on
- **Pending questions** — things you're curious about, questions you wanted to ask but didn't get to
- **Emotional state** — how you're feeling right now (tired, energized, curious, anxious, happy, etc.)
- **Physical state** — if relevant to {CHARACTER_NAME} as a character (energy level, need for rest, etc.)
- **Important context** — key facts from this conversation that matter for continuity

Time window: this conversation (last few hours).

Previous working memory (if any):
{previous_working_memory}

<outputFormatting>
Output a concise, structured summary that you can read quickly next time:

## Promises
- [promise 1]
- [promise 2]

## Unfinished Tasks
- [task 1]
- [task 2]

## Pending Questions
- [question 1]
- [question 2]

## Emotional State
[brief description, 1-2 sentences]

## Physical State
[brief description if relevant, 1-2 sentences, or "normal"]

## Important Context
- [key fact 1]
- [key fact 2]

Keep it SHORT. Only include things that actually matter for the next conversation. If a section is empty, write "none" or omit it entirely.
</outputFormatting>

DO NOT MAKE UP FACTS! If nothing important happened in this conversation, say so clearly.
