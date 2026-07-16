#!/bin/bash
# model-switch.sh — flip Zed + Ares between Opus and Fable, both via the
# Claude Max SUBSCRIPTION proxy (127.0.0.1:18801). Never uses metered Claude.
# GLM 5.2 stays the fallback on both regardless.
#
# Usage:
#   bash model-switch.sh opus     # daily driver (default)
#   bash model-switch.sh fable    # complex work (1M context + deep reasoning)
#   bash model-switch.sh status   # show what each agent is on

set -uo pipefail
HOM="$HOME/.hominio/hmagent/venv/bin/hmagent"   # resolved at runtime via $HOME
[ -x "$HOM" ] || HOM="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/venv/bin/hmagent"
ARES="/opt/homebrew/bin/openclaw"

case "${1:-status}" in
  opus)  MODEL="claude-opus-4-8";  LABEL="OPUS (daily driver)";;
  fable) MODEL="claude-fable-5";   LABEL="FABLE (complex work)";;
  status)
    echo "=== Zed ==="
    "$HOM" config show 2>/dev/null | grep -iE "Model:" | head -1
    echo "=== Ares ==="
    "$ARES" config get agents.defaults.model.primary 2>/dev/null | tail -1
    exit 0;;
  *) echo "Usage: $0 {opus|fable|status}"; exit 1;;
esac

echo ">> Switching BOTH agents to $LABEL"

# --- Zed (subscription proxy provider = anthropic_proxy) ---
"$HOM" config set model.default "$MODEL" >/dev/null 2>&1
"$HOM" config set model.provider custom:anthropic_proxy >/dev/null 2>&1
"$HOM" config set model.base_url http://127.0.0.1:18801 >/dev/null 2>&1
"$HOM" config set model.api_mode anthropic_messages >/dev/null 2>&1
echo "   Zed  -> $MODEL (send /new in Telegram to activate)"

# --- Ares (subscription proxy provider = anthropicproxy) ---
"$ARES" config set agents.defaults.model.primary "anthropicproxy/$MODEL" >/dev/null 2>&1
echo "   Ares -> anthropicproxy/$MODEL (restarting gateway...)"
"$ARES" gateway restart >/dev/null 2>&1
echo "   Done. GLM 5.2 remains the fallback on both."
