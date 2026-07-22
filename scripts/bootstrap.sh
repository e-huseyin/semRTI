#!/usr/bin/env bash
# Fill in the {{PLACEHOLDER}} tokens scattered across this template with
# project-specific values, so a new INFINITY component repository starts
# already populated instead of full of blanks.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ask() {
    local prompt="$1" default="${2:-}" var
    if [ -n "$default" ]; then
        read -r -p "$prompt [$default]: " var
        echo "${var:-$default}"
    else
        read -r -p "$prompt: " var
        echo "$var"
    fi
}

echo "== INFINITY component bootstrap =="
echo "Leave a field blank and edit the file later if you're not ready to answer."
echo

PROJECT_NAME=$(ask "Repository / component name (lowercase-hyphenated)")
DESCRIPTION=$(ask "One-sentence description")
COMPONENT_TYPE=$(ask "Component type (Data|Application|Software|Report|Dataset|Ontology|KnowledgeGraph)" "Software")
COMPONENT_ID=$(ask "component-id" "${PROJECT_NAME}")
WORK_PACKAGE=$(ask "Work package (e.g. WP4)")
PILOT=$(ask "Pilot name")
CHAMPION_NAME=$(ask "Champion full name")
CHAMPION_ORG=$(ask "Champion organisation")
CHAMPION_EMAIL=$(ask "Champion email")
REPO_URL=$(ask "Repository URL" "https://codeberg.org/infinity-project/${PROJECT_NAME}")
LICENCE=$(ask "SPDX licence identifier (for LICENSE/codemeta/CITATION.cff)" "EUPL-1.2")

# component.md's `licence:` field must be a code from REECO's own vocabulary
# (reeco-python/src/reeco/schema/licences.yml), which is NOT SPDX and, as of
# this writing, has no EUPL code at all. Suggest a sensible REECO code based
# on the SPDX choice above, but always let the user confirm/override.
case "$LICENCE" in
    MIT) reeco_default="MIT" ;;
    Apache-2.0) reeco_default="Apache-2.0" ;;
    GPL-3.0*) reeco_default="GNU_GPL_v3" ;;
    AGPL-3.0*) reeco_default="AGPL" ;;
    EUPL-1.2) reeco_default="GNU_GPL_v3" ;;  # closest REECO code; see component.md notes
    *) reeco_default="GNU_GPL_v3" ;;
esac
REECO_LICENCE_CODE=$(ask "REECO licence code for component.md (see component.md notes on the SPDX/REECO mismatch)" "$reeco_default")

RELEASE_NUMBER=$(ask "Initial release number" "v0.1.0-alpha")
CHANGELOG_URL=$(ask "Changelog URL" "${REPO_URL}/src/branch/main/CHANGELOG.md")
RELEASE_DATE=$(date +%Y/%m/%d)
YEAR=$(date +%Y)

CHAMPION_GIVEN_NAME="${CHAMPION_NAME%% *}"
CHAMPION_FAMILY_NAME="${CHAMPION_NAME#* }"
[ "$CHAMPION_FAMILY_NAME" = "$CHAMPION_NAME" ] && CHAMPION_FAMILY_NAME=""

echo
echo "Applying values..."

replace() {
    local key="$1" value="$2"
    # Escape sed metacharacters in the replacement value.
    local escaped
    escaped=$(printf '%s' "$value" | sed -e 's/[\/&]/\\&/g')
    # scripts/ is excluded: validate.sh and this script reference {{KEY}}
    # tokens literally in their own logic/messages, not as unfilled fields.
    grep -rlZ --exclude-dir=.git --exclude-dir=scripts "{{${key}}}" . 2>/dev/null | while IFS= read -r -d '' f; do
        sed -i "s/{{${key}}}/${escaped}/g" "$f"
    done
}

replace "PROJECT_NAME" "$PROJECT_NAME"
replace "DESCRIPTION" "$DESCRIPTION"
replace "COMPONENT_TYPE" "$COMPONENT_TYPE"
replace "COMPONENT_ID" "$COMPONENT_ID"
replace "WORK_PACKAGE" "$WORK_PACKAGE"
replace "PILOT" "$PILOT"
replace "CHAMPION_NAME" "$CHAMPION_NAME"
replace "CHAMPION_ORG" "$CHAMPION_ORG"
replace "CHAMPION_EMAIL" "$CHAMPION_EMAIL"
replace "CHAMPION_GIVEN_NAME" "$CHAMPION_GIVEN_NAME"
replace "CHAMPION_FAMILY_NAME" "$CHAMPION_FAMILY_NAME"
replace "REPO_URL" "$REPO_URL"
replace "LICENCE" "$LICENCE"
replace "REECO_LICENCE_CODE" "$REECO_LICENCE_CODE"
replace "RELEASE_NUMBER" "$RELEASE_NUMBER"
replace "RELEASE_DATE" "$RELEASE_DATE"
replace "CHANGELOG_URL" "$CHANGELOG_URL"
replace "YEAR" "$YEAR"
replace "LATEST_MAJOR" "0"

echo
echo "Done. Remaining placeholders (fill in manually, or leave until they apply):"
grep -rlo --exclude-dir=.git --exclude-dir=scripts '{{[A-Z_]*}}' . 2>/dev/null | sort -u || echo "  (none left)"
echo
echo "Next steps:"
echo "  1. Review README.md, MAINTAINERS.md, component.md, codemeta.json, CITATION.cff, AI_USAGE.md/ai.txt"
echo "  2. Fill in docs/ethics/digital-heritage-ethics-declaration.md"
echo "  3. Run ./scripts/validate.sh"
echo "  4. git init (if not already) && git add -A && git commit"
