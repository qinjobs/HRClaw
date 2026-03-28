# Shell env config (can be sourced directly)
export SCREENING_EXTRACTION_PROVIDER=kimi_cli
export SCREENING_EXTRACTION_MODEL=kimi-for-coding
export SCREENING_KIMI_CLI_COMMAND=/Users/jobs/.local/bin/kimi
export SCREENING_KIMI_CLI_ARGS="--print --output-format text --final-message-only"
export SCREENING_KIMI_CLI_TIMEOUT_SECONDS=180
export SCREENING_AUTO_GREET_THRESHOLD=90
export SCREENING_AUTO_GREET_ALLOW_NON_RECOMMEND=0

# Optional: provide API key to auto-generate Kimi CLI provider config (avoid interactive /login)
export SCREENING_KIMI_CLI_API_KEY=sk-kimi-RNehyskyNaVTcasx48V0PmtE49hDFrg0hj4zzr1HDKv4Mx3fBYEjF2KSCtDqZ0g1
export SCREENING_KIMI_CLI_BASE_URL=https://api.kimi.com/coding/v1
# Optional: custom CLI config JSON/TOML. If omitted, project auto-generates a full config from API key.
# export SCREENING_KIMI_CLI_CONFIG='{"default_model":"kimi-for-coding","providers":{"kimi-for-coding":{"type":"kimi","base_url":"https://api.kimi.com/coding/v1","api_key":"sk-kimi-xxx"}},"models":{"kimi-for-coding":{"provider":"kimi-for-coding","model":"kimi-for-coding","max_context_size":262144}}}'

# Optional fallback: OpenAI-compatible extraction (only when explicitly needed)
# export SCREENING_EXTRACTION_PROVIDER=openai_compatible
# export SCREENING_LLM_API_KEY=your_api_key
# export SCREENING_LLM_BASE_URL=https://your-compatible-endpoint/v1
