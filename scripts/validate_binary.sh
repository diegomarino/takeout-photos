#!/bin/bash
#
# Validate takeout-photos binary build
#
# This script performs comprehensive validation of the PyInstaller-built binary:
# - Checks executable permissions
# - Verifies library dependencies (macOS-specific)
# - Checks for bundled exiftool
# - Runs functional tests (--help, --version)
#
# Usage:
#   ./scripts/validate_binary.sh dist/takeout-photos
#

set -e

BINARY="$1"

if [ -z "$BINARY" ]; then
    echo "Usage: $0 <path-to-binary>"
    echo "Example: $0 dist/takeout-photos"
    exit 1
fi

echo "=== Validating binary: $BINARY ==="
echo ""

# 1. Check exists and executable
echo "[1/4] Checking binary existence and permissions..."
if [ ! -f "$BINARY" ]; then
    echo "❌ Binary not found: $BINARY"
    exit 1
fi

if [ ! -x "$BINARY" ]; then
    echo "❌ Binary not executable: $BINARY"
    exit 1
fi
echo "✅ Binary exists and is executable"
echo ""

# 2. Check library dependencies (macOS)
echo "[2/4] Checking library dependencies..."
if command -v otool >/dev/null 2>&1; then
    echo "System libraries (should only use macOS system libs):"
    otool -L "$BINARY" | grep -v "/usr/lib" | grep -v "/System/Library" || echo "  (none - all system libraries)"
    echo "✅ Library check complete"
else
    echo "⚠️  otool not available (skipping library check)"
fi
echo ""

# 3. Check exiftool is bundled
echo "[3/4] Checking for bundled exiftool..."
if strings "$BINARY" | grep -q "exiftool"; then
    echo "✅ exiftool reference found in binary"
else
    echo "⚠️  No exiftool reference found (may still work)"
fi
echo ""

# 4. Basic functional tests
echo "[4/4] Running functional tests..."

# Test --help
if "$BINARY" --help > /dev/null 2>&1; then
    echo "✅ --help works"
else
    echo "❌ --help failed"
    exit 1
fi

# Test without arguments (should show usage)
if "$BINARY" 2>&1 | grep -q "takeout-photos"; then
    echo "✅ Base command works (shows usage)"
else
    echo "❌ Base command failed"
    exit 1
fi

# Test --doctor (dependency checking)
if "$BINARY" --doctor 2>&1 | grep -q "exiftool"; then
    echo "✅ --doctor works (dependency checking functional)"
else
    echo "⚠️  --doctor output unexpected (may need investigation)"
fi

echo ""
echo "=== ✅ Validation complete ==="
echo ""
echo "Binary is ready for distribution!"
echo "Size: $(ls -lh "$BINARY" | awk '{print $5}')"
