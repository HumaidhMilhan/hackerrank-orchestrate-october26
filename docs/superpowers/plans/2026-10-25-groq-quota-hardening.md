# Groq quota and observer hardening

Implements the user priority table; supersedes earlier strict-vision/cap and estimated-COMPLETE defaults where specified.

1. Test then fix per-model minute usage settlement, authoritative header bounds, cached-token exclusion and in-flight-safe scheduling. Preserve conservative unknown failures, daily accounting and Gemini compatibility.
2. Test then fix vision JSON Object mode/local validation, compact prompt, text caps256/512 and batches4, configurable bounded transient retry budget, safe detailed diagnostics. No validation retry. Keep Qwen512/none and separate model buckets.
3. Test then prevent COMPLETE when eligible observer extraction fails, preserving observed facts and avoiding invented findings. Add explicit observation-failure marker from stage3.
4. Create clean .venv, install compatible dependencies, freeze requirements.lock, verify pip check/tests without warnings. Keep user artifacts unchanged.
5. Verify real model calls/headers and isolated sample runner, perform one independent review and one fix pass if needed, refresh docs/archive, commit selected source only.

Review focus: concurrent headers must not grant duplicate tokens; stale/missing headers must not erase reservations; request headers represent RPD not RPM; JSON errors must not leak contents or retry; observer failure must not create a positive completion verdict.

Completed:94 tests pass; clean lock installs/pip check; independent review4Important findings fixed in one pass; isolated live32-case run and extracted offline32-case smoke completed. Live coverage remains limited by requested256-token primary cap and accumulated local daily reservations; these were not silently raised/reset. Root predictions/reports preserved.
