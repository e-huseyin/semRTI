#!/usr/bin/env bash
# Check this repository against the mandatory and recommended requirements of the
# Technical Rulebook for INFINITY Developers. Exits non-zero if a mandatory check fails.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FAIL=0
WARN=0

ok()   { printf "  [OK]   %s\n" "$1"; }
fail() { printf "  [FAIL] %s\n" "$1"; FAIL=$((FAIL+1)); }
warn() { printf "  [WARN] %s\n" "$1"; WARN=$((WARN+1)); }

require_file() {
    if [ -f "$1" ]; then ok "$1 present"; else fail "$1 is missing (mandatory)"; fi
}

recommend_file() {
    if [ -f "$1" ]; then ok "$1 present"; else warn "$1 is missing (recommended)"; fi
}

echo "== Mandatory repository files =="
require_file "README.md"
require_file "LICENSE"
require_file "CONTRIBUTING.md"
require_file "MAINTAINERS.md"
require_file "CODE_OF_CONDUCT.md"
require_file "CHANGELOG.md"

echo
echo "== Recommended repository files =="
recommend_file "SECURITY.md"
recommend_file "SUPPORT.md"
recommend_file "AI_USAGE.md"
recommend_file "ai.txt"
recommend_file ".editorconfig"
recommend_file ".gitignore"

echo
echo "== Component metadata (REECO Ecosystem schema) =="
if [ -f "component.md" ]; then
    head -n1 "component.md" | grep -q '^---$' && ok "component.md has a YAML front-matter block" \
        || fail "component.md does not start with a '---' YAML front-matter delimiter"

    # Mandatory per reeco.Validator().asComponent(): component-id, name,
    # description, type, licence, related-components.
    for key in component-id name description type licence related-components; do
        grep -qE "^${key}:" component.md \
            && ok "component.md has '${key}:'" \
            || fail "component.md is missing mandatory REECO key '${key}:'"
    done

    # Best-effort deep check against the real REECO validator, if available
    # locally (pip install reeco python-frontmatter). This is the same check
    # the ecosystem site runs at build time; not required to run validate.sh.
    if python3 -c "import reeco, frontmatter" >/dev/null 2>&1; then
        python3 - "component.md" <<'PYEOF'
import sys, frontmatter, reeco
with open(sys.argv[1], encoding="utf-8") as f:
    data, _ = frontmatter.parse(f.read())
v = reeco.Validator()
is_container = "container-id" in data
result = v.asContainer(data) if is_container else v.asComponent(data)
errors = result.get("error", [])
warnings = result.get("warning", [])
for e in errors:
    print("  [FAIL] reeco:", str(e).strip().splitlines()[0])
for w in warnings:
    print("  [WARN] reeco:", str(w).strip().splitlines()[0])
if not errors:
    print("  [OK]   component.md passes reeco.Validator()")
sys.exit(1 if errors else 0)
PYEOF
        if [ $? -ne 0 ]; then FAIL=$((FAIL+1)); else true; fi
    else
        echo "  [--]   reeco not installed locally (pip install reeco python-frontmatter) — skipping live schema check"
    fi
else
    fail "no component-annotation markdown file found (expected component.md, but any filename with a YAML header is valid)"
fi
recommend_file "codemeta.json"
if [ -f "codemeta.json" ]; then
    if command -v python3 >/dev/null 2>&1; then
        python3 -m json.tool codemeta.json >/dev/null 2>&1 && ok "codemeta.json is valid JSON" \
            || fail "codemeta.json is not valid JSON"
    else
        warn "python3 not available to validate codemeta.json syntax"
    fi
fi
recommend_file "CITATION.cff"

echo
echo "== Testing =="
if [ -d "tests" ] && [ -n "$(find tests -type f ! -name 'README.md' 2>/dev/null)" ]; then
    ok "tests/ contains test files"
else
    warn "tests/ has no test files yet (only scaffold present)"
fi

echo
echo "== Continuous Integration =="
if [ -d ".forgejo/workflows" ] && [ -n "$(find .forgejo/workflows -type f 2>/dev/null)" ]; then
    ok ".forgejo/workflows contains at least one workflow"
else
    fail "no Forgejo Actions workflow found under .forgejo/workflows/"
fi

echo
echo "== Governance =="
if [ -f "MAINTAINERS.md" ] && ! grep -q '{{CHAMPION_NAME}}' MAINTAINERS.md; then
    ok "Champion appears to be filled in"
elif [ -f "MAINTAINERS.md" ]; then
    warn "Champion placeholder still present in MAINTAINERS.md — run scripts/bootstrap.sh"
fi

echo
echo "== Ethics =="
if [ -f "docs/ethics/digital-heritage-ethics-declaration.md" ]; then
    ok "Digital Heritage Ethics Declaration template present"
    grep -q '{{DECLARATION_DATE}}' "docs/ethics/digital-heritage-ethics-declaration.md" 2>/dev/null \
        && warn "Ethics declaration not yet filled in (still has placeholders)"
else
    fail "docs/ethics/digital-heritage-ethics-declaration.md is missing"
fi

echo
echo "== Leftover placeholders =="
LEFTOVER=$(grep -rlo --exclude-dir=.git --exclude-dir=scripts '{{[A-Z_]*}}' . 2>/dev/null | sort -u)
if [ -n "$LEFTOVER" ]; then
    warn "Placeholder tokens still present in:"
    echo "$LEFTOVER" | sed 's/^/         /'
else
    ok "No leftover {{PLACEHOLDER}} tokens"
fi

echo
echo "=================================="
echo "Result: $FAIL failing (mandatory), $WARN warnings (recommended)"
if [ "$FAIL" -gt 0 ]; then
    echo "Rulebook compliance: FAIL"
    exit 1
else
    echo "Rulebook compliance: PASS (warnings should still be reviewed before release)"
    exit 0
fi
