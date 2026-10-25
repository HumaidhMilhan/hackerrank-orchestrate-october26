# Final full-dataset run: model usage

Run: 2026-10-24T20:27:04.353261+00:00

Requests: 518. Mode: evaluation.

| Provider/model | Calls | Input | Output | Thinking | Cached input | Unknown usage calls | Estimated USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gemini/gemini-3.6-flash | 36 | 16629 | 9473 | 24643 | 0 | 8 | unavailable |

Overall calls: 36; input tokens: 16629; output tokens: 9473; thinking tokens: 24643.
Total reported tokens: 50745; average per request: 97.963.
Estimated total USD: None; per request: None.

Accepted response-cache hits: 2; evidence extraction cache hits: 83.

Actual calls attributable to this logical run; resumed checkpoints retain prior calls. Reused extraction from earlier runs is not billed again. Missing provider usage is not zero.

SDK operation counts: {"count_tokens": 14, "generate_content": 22}. Gemini token-count requests count toward local RPM/concurrency and reserve generation input TPM. They do not contribute generated-model input/output totals. Groq reserves combined input/output TPM and daily budgets; reasoning is already included in completion tokens. Failed requests retain conservative reservations.

Task counts (including secondary intent evaluation): {"intent": 36}.

Costs require explicitly configured verified per-million rates. A free tier may have zero money cost but nonzero quota/token usage. Unknown token usage is excluded from numerical totals and disclosed above. Cached extraction construction cost from previous runs is not included in this run; record those earlier runs separately when calculating total project expenditure. Offline runs do not verify live model/vision accuracy.
