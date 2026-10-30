# Tool feedback log (for the required Devpost feedback section)

Format: date/time SGT · tool · what happened · impact · suggestion.

## Nebius Token Factory
- 30 Oct, pre-flight · **Case-sensitive model IDs that differ from the expected/announced ID.** Ultra is `nvidia/Nemotron-3-Ultra-550b-a55b`, but the expected ID was `nvidia/nemotron-3-ultra-550b-a55b`. Nano and Super use different casing conventions from each other (`NVIDIA-Nemotron-3-Nano-30B-A3B` vs `nemotron-3-super-120b-a12b`). · A wrong ID costs a debug cycle. · Suggest case-insensitive ID matching, or a "did you mean" suggestion in the 404 body.
- 30 Oct, pre-flight · **Reasoning tokens silently consume `max_tokens`.** When the budget runs out during reasoning, `message.content` comes back empty, and the only signal is `finish_reason=length`. · It looks like a broken response, not a budget problem. · Suggest documenting this in the quickstart, or a separate reasoning budget parameter.
- 30 Oct 7:20 PM · **`chat_template_kwargs.enable_thinking=false` works on Nano via `extra_body`.** Completion tokens went from 227 to 25 and latency from 6.4 s to 3.7 s on the same prompt, with output still valid. · A big cost win, but undocumented. I found it from the model card's chat template, not from Token Factory docs. · Suggest documenting per-model reasoning controls in the API reference.
- 30 Oct 7:20 PM · **Reasoning is exposed inconsistently.** Super returns `reasoning_content` on the message; Nano (thinking on) returned no `reasoning_content` and no `<think>` text, yet billed 227 completion tokens for a one-line answer. · Hard to see where tokens go. · Suggest consistent `reasoning_content`, or a `usage.reasoning_tokens` field.
- 30 Oct 7:20 PM · Positive: Super answered in 0.8 s, and all three tiers returned valid JSON from prompt instructions alone.

## NVIDIA Nemotron models
- (see Token Factory entries; add model-quality notes here)

## Tavily
- 30 Oct, pre-flight · **Extract on the Devpost rules page works (~40K chars) but includes markdown and image noise** (image links, nav, badges). · It inflates tokens sent to the LLM. · Suggest a "main content only" or "strip images/links" option on extract.
