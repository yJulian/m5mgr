# Source this file (do not execute it) to make the `m5mgr` command
# available in your shell, without manually activating the venv each time:
#
#   source /home/julian/Development/m5mgr/shell-setup.sh
#
# To make this permanent, add that line to your ~/.bashrc (or ~/.zshrc):
#
#   echo 'source /home/julian/Development/m5mgr/shell-setup.sh' >> ~/.bashrc
#
# This just prepends the project's venv/bin to PATH, so `m5mgr` (and
# `python`/`pip`/`pytest` from that venv) resolve without `source
# .venv/bin/activate` and without a (venv) prompt prefix change.

_m5mgr_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

if [ -x "$_m5mgr_dir/.venv/bin/m5mgr" ]; then
  case ":$PATH:" in
    *":$_m5mgr_dir/.venv/bin:"*) ;;
    *) export PATH="$_m5mgr_dir/.venv/bin:$PATH" ;;
  esac
else
  echo "m5mgr: no venv found at $_m5mgr_dir/.venv - run:" >&2
  echo "  python3 -m venv $_m5mgr_dir/.venv && $_m5mgr_dir/.venv/bin/pip install -e \"$_m5mgr_dir[dev]\"" >&2
fi

unset _m5mgr_dir
