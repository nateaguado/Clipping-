#!/bin/bash
# One-time setup for the GTA 6 Clipper by MIRFAN Studios. Safe to run again: anything already installed is skipped.
# It needs no password and no admin rights: everything goes into ~/.stream-clipper.
#   bash setup.sh           install what is missing, then print READY
#   bash setup.sh --check   print READY if everything is installed (fast), else NOT READY
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# uv: a small tool that downloads Python and the packages the editor uses, without touching the system
if ! command -v uv >/dev/null 2>&1; then
  [ "${1:-}" = "--check" ] && { echo "NOT READY: missing uv"; exit 1; }
  echo "Step 1 of 6: getting the installer helper (uv)..."
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" ;;
    *) curl -LsSf https://astral.sh/uv/install.sh | sh ;;
  esac
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || { echo "NOT READY: could not install uv (check the internet connection, then run setup again)"; exit 1; }

exec uv run --quiet --no-project --python 3.11 python "$HERE/setup.py" "$@"
