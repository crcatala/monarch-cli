#!/usr/bin/env bash
set -euo pipefail

# Release script for monarch-cli
# Creates GitHub release with tag and changelog (does NOT publish to PyPI)
#
# Usage: ./scripts/release.sh [--dry-run]
#
# After running this, publish to PyPI separately:
#   uv run twine upload dist/*

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "🔍 DRY RUN MODE - no changes will be made"
    echo ""
fi

# Get version from package
VERSION=$(grep -m1 '__version__' src/monarch_cli/__init__.py | cut -d'"' -f2)
TAG="v${VERSION}"

echo "📦 Preparing release for monarch-cli ${VERSION}"
echo ""

# The git tag is derived from the package source version, but the built
# wheel/sdist version comes from pyproject.toml. If they drift, the tag and the
# published artifact would disagree. Fail early with an actionable message.
PYPROJECT_VERSION=$(grep -m1 '^version' pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/')
if [[ "$VERSION" != "$PYPROJECT_VERSION" ]]; then
    echo "❌ Version mismatch:"
    echo "   src/monarch_cli/__init__.py: ${VERSION}"
    echo "   pyproject.toml:             ${PYPROJECT_VERSION}"
    echo ""
    echo "   The git tag is derived from src/monarch_cli/__init__.py, while the"
    echo "   built wheel/sdist version comes from pyproject.toml. Make them match"
    echo "   (and refresh uv.lock with 'uv lock') before releasing."
    echo "   See docs/RELEASING.md, Step 1."
    exit 1
fi

# Check if tag already exists
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "❌ Tag $TAG already exists!"
    echo "   Either bump the version or delete the existing tag."
    exit 1
fi

# Check for uncommitted changes
if [[ -n $(git status --porcelain) ]]; then
    echo "❌ Uncommitted changes detected. Please commit or stash first."
    git status --short
    exit 1
fi

# Check we're on main
BRANCH=$(git branch --show-current)
if [[ "$BRANCH" != "main" ]]; then
    echo "⚠️  Warning: You're on branch '$BRANCH', not 'main'"
    read -p "   Continue anyway? [y/N] " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || exit 1
fi

# Extract changelog for this version
echo "📝 Extracting changelog for ${VERSION}..."
CHANGELOG=$(sed -n "/^## \[${VERSION}\]/,/^## \[/p" CHANGELOG.md | head -n -1)

if [[ -z "$CHANGELOG" ]]; then
    echo "❌ No changelog entry found for version ${VERSION}"
    echo "   Add an entry to CHANGELOG.md first."
    exit 1
fi

echo "─────────────────────────────────────────"
echo "$CHANGELOG"
echo "─────────────────────────────────────────"
echo ""

# Build package and verify the wheel installs cleanly (canonical target)
echo "🔨 Building package and smoke-installing wheel..."
if [[ "$DRY_RUN" == false ]]; then
    rm -rf build/ *.egg-info
    # smoke-install wipes and rebuilds dist/, so artifacts always match the
    # current metadata; there is no stale-dist risk on this path.
    make smoke-install
    uv run twine check dist/*

    # Belt and braces: the artifact we are about to attach must be the version
    # we are about to tag.
    if ! ls dist/monarch_cli-"${VERSION}"-*.whl >/dev/null 2>&1; then
        echo "❌ Built wheel does not match version ${VERSION}."
        echo "   dist/ contains:"
        ls -1 dist/
        echo "   Fix the version metadata and re-run (see docs/RELEASING.md Step 1)."
        exit 1
    fi
else
    echo "   [dry-run] Would run: make smoke-install && twine check dist/*"
fi
echo ""

# Confirm release
echo "🚀 Ready to create GitHub release (not PyPI):"
echo "   • Create git tag: $TAG"
echo "   • Push tag to origin"
echo "   • Create GitHub release with changelog"
echo "   • Upload dist/*.whl and dist/*.tar.gz as release assets"
echo ""

if [[ "$DRY_RUN" == false ]]; then
    read -p "Proceed with release? [y/N] " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || exit 1
fi

# Create and push tag
echo ""
echo "🏷️  Creating tag ${TAG}..."
if [[ "$DRY_RUN" == false ]]; then
    git tag -a "$TAG" -m "Release ${VERSION}"
    git push origin "$TAG"
else
    echo "   [dry-run] Would run: git tag -a $TAG -m 'Release ${VERSION}'"
    echo "   [dry-run] Would run: git push origin $TAG"
fi

# Create GitHub release
echo "📢 Creating GitHub release..."
if [[ "$DRY_RUN" == false ]]; then
    gh release create "$TAG" dist/* \
        --title "$TAG" \
        --notes "$CHANGELOG"
else
    echo "   [dry-run] Would run: gh release create $TAG dist/* --title $TAG --notes <changelog>"
fi

echo ""
echo "✅ GitHub release ${VERSION} complete!"
echo ""
echo "   View release: https://github.com/crcatala/monarch-cli/releases/tag/${TAG}"
echo ""
echo "⚠️  This script does NOT publish to PyPI. To publish:"
echo ""
echo "   uv run twine upload dist/*"
echo ""
