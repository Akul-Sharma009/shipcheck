# Tool feedback log (for the required Devpost feedback section)

Format: date/time SGT · tool · what happened · impact · suggestion.

## Nebius Token Factory
- 30 Oct, pre-flight · **Case-sensitive model IDs that differ from the expected/announced ID.** Ultra is `nvidia/Nemotron-3-Ultra-550b-a55b`, but the expected ID was `nvidia/nemotron-3-ultra-550b-a55b`. Nano and Super use different casing conventions from each other (`NVIDIA-Nemotron-3-Nano-30B-A3B` vs `nemotron-3-super-120b-a12b`). · A wrong ID costs a debug cycle. · Suggest case-insensitive ID matching, or a "did you mean" suggestion in the 404 body.
- 30 Oct, pre-flight · **Reasoning tokens silently consume `max_tokens`.** When the budget runs out during reasoning, `message.content` comes back empty, and the only signal is `finish_reason=length`. · It looks like a broken response, not a budget problem. · Suggest documenting this in the quickstart, or a separate reasoning budget parameter.
- 30 Oct 7:20 PM · **`chat_template_kwargs.enable_thinking=false` works on Nano via `extra_body`.** Completion tokens went from 227 to 25 and latency from 6.4 s to 3.7 s on the same prompt, with output still valid. · A big cost win, but undocumented. I found it from the model card's chat template, not from Token Factory docs. · Suggest documenting per-model reasoning controls in the API reference.
- 30 Oct 7:20 PM · **Reasoning is exposed inconsistently.** Super returns `reasoning_content` on the message; Nano (thinking on) returned no `reasoning_content` and no `<think>` text, yet billed 227 completion tokens for a one-line answer. · Hard to see where tokens go. · Suggest consistent `reasoning_content`, or a `usage.reasoning_tokens` field.
- 30 Oct 8:00 PM · **Super with reasoning on ran out of a 6000-token budget mid-JSON** on a 40K-char rules page, and spent 14K output tokens over 69 s across 2 calls. With `enable_thinking=false`: 2.5K tokens in 11 s, comparable output. · Reasoning-on is the default and is expensive for extraction tasks. · Suggest documenting the reasoning toggle and a recommended max_tokens per model in the model card on Token Factory.
- 30 Oct 8:00 PM · **Rules extraction from the same page isn't stable from run to run** (16, 17 or 19 requirements). · Results have to be cached for a consistent UX. · Suggest a `seed` parameter (if supported, document it).
- 30 Oct 7:20 PM · Positive: Super answered in 0.8 s, and all three tiers returned valid JSON from prompt instructions alone.

## NVIDIA Nemotron models
- 30 Oct 8:30 PM · **Nano (thinking off) copies the example values from the prompt into its answers.** Given "e.g. Nebius Token Factory, Tavily, GitHub API, OpenAI" as examples for apis_called, it listed all four for requirements.txt, docker-compose.yml and JS files that call none of them. · A silent false-evidence risk. · Workaround: removed the examples and dropped any claim whose name doesn't appear in the file. Model cards could warn about example-copying at small sizes.
- 30 Oct 8:30 PM · Nano occasionally returns markdown prose instead of the requested JSON object (1 in ~30 calls); one retry with the error fixed it every time.
- 30 Oct 8:40 PM · Positive: **Super's verdicts cite exact path:line evidence when given grep lines with line numbers.** In a spot check, both citations (Token Factory base URL, Nemotron model ID) were the right lines. Super without thinking gave 2.5K-token rules in about 10 s; Super with thinking gave verdicts in about 25 s.
- 30 Oct 8:40 PM · Cost per full run (17 requirements, 26 files): Nano 26 calls, ~65K in / 3.6K out; Super 2 calls, ~20K in / ~3.8K out; about 37 s wall time.

## Tavily
- 30 Oct 8:25 PM · Positive: the same Extract + cleaning worked unchanged on two other Devpost hackathons (PayPal AI, Atlassian Codegeist). Both pages were extracted, and Super produced correct dates, requirements and criteria in about 5 s each.
- 30 Oct 7:50 PM · Extracting the Devpost overview + rules in one call worked first time (10K + 40K chars). About 6K chars of each page was Devpost's site navigation, repeated twice per page, above the actual content. Dropping everything above the first H1 plus deduplicating lines removed it. · Suggest an `extract_depth`/"main content only" mode that drops site chrome.
- 30 Oct, pre-flight · **Extract on the Devpost rules page works (~40K chars) but includes markdown and image noise** (image links, nav, badges). · It inflates tokens sent to the LLM. · Suggest a "main content only" or "strip images/links" option on extract.
