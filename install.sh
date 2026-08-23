#!/bin/sh
# Install the Work Items CLI without sudo.
set -eu

VERSION="v0.0.2"
VERSION_NUMBER="${VERSION#v}"
WHEEL="work_items-${VERSION_NUMBER}-py3-none-any.whl"
URL="https://github.com/TinyWhite1997/work-items/releases/download/${VERSION}/${WHEEL}"
SHA256="c306b8497d8383ce755d05a36ea1a63c8307b87cc8acf63d177cbf09ef428296"
PYTHON="${PYTHON:-python3}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="${WORK_ITEMS_INSTALL_DIR:-$DATA_HOME/work-items/venv}"
BIN_DIR="${WORK_ITEMS_BIN_DIR:-$HOME/.local/bin}"

command -v "$PYTHON" >/dev/null || { echo "Python 3.10+ is required." >&2; exit 1; }
"$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' || { echo "Python 3.10+ is required." >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required." >&2; exit 1; }

tmpdir=$(mktemp -d)
tmp="$tmpdir/$WHEEL"
trap 'rm -rf "$tmpdir"' EXIT HUP INT TERM
curl -fsSL "$URL" -o "$tmp"
"$PYTHON" - "$tmp" "$SHA256" <<'PY'
import hashlib, pathlib, sys
actual = hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest()
if actual != sys.argv[2]:
    raise SystemExit(f"Refusing download: SHA-256 mismatch ({actual})")
PY

"$PYTHON" -m venv "$INSTALL_DIR"
"$INSTALL_DIR/bin/pip" install --quiet --upgrade "$tmp"
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/bin/work-items" "$BIN_DIR/work-items"

echo "Installed work-items to $BIN_DIR/work-items"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Add $BIN_DIR to PATH, then run: work-items daemon" ;;
esac
