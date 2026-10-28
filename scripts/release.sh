#!/usr/bin/env bash
# Release script for monarch-cli.
#
# Creates the git tag and GitHub release (does NOT publish to PyPI). Publishing
# is the last, separate step, from the same dist/ built from the tagged commit:
#
#   uv run twine upload dist/*
#
# Usage: ./scripts/release.sh [--dry-run]
#
# Preflight, in order: version metadata agrees, clean tree, main, HEAD equals
# origin/main, tag absent, a changelog section for the version exists, and the
# wheel/sdist build is stamped with HEAD. The tag is annotated "Release X.Y.Z"
# and the GitHub Release uses the changelog section as its notes.
set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "🔍 DRY RUN MODE - no changes will be made"
    echo ""
fi

warn() { printf '⚠️  %s\n' "$*"; }
fail() {
    printf '❌ %s\n' "$*" >&2
    exit 1
}

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
    echo "   (and refresh uv.lock with 'uv lock') before releasing; 'make bump'"
    echo "   updates all three together."
    echo "   See RELEASING.md."
    exit 1
fi

# Check for uncommitted changes
if [[ -n $(git status --porcelain) ]]; then
    echo "❌ Uncommitted changes detected. Please commit or stash first."
    git status --short
    exit 1
fi

# A real release is cut from main, at the commit that was pushed.
BRANCH=$(git branch --show-current)
if [[ "$BRANCH" != "main" ]]; then
    if [[ "$DRY_RUN" == true ]]; then
        warn "dry run on branch '$BRANCH', not 'main' (a real release would refuse)."
    else
        fail "releases are cut from main, not '$BRANCH'."
    fi
fi

if [[ "$DRY_RUN" == false ]]; then
    git fetch --quiet origin main
    if [[ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]]; then
        fail "HEAD is not origin/main; push the release commit (git push) first."
    fi
elif [[ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main 2>/dev/null || true)" ]]; then
    warn "dry run: HEAD is not origin/main (a real release would refuse)."
fi

# Check if tag already exists. A dry run on an already-released version still
# previews every step; a real release must bump first.
if git rev-parse "$TAG" >/dev/null 2>&1; then
    if [[ "$DRY_RUN" == true ]]; then
        warn "dry run: tag ${TAG} already exists; a real release must bump the version first."
    else
        fail "tag ${TAG} already exists; bump the version or delete the existing tag."
    fi
fi

# Extract changelog for this version
echo "📝 Extracting changelog for ${VERSION}..."
CHANGELOG=$(sed -n "/^## \[${VERSION}\]/,/^## \[/p" CHANGELOG.md | head -n -1)

if [[ -z "$CHANGELOG" ]]; then
    fail "no changelog entry found for version ${VERSION}; add one to CHANGELOG.md first."
fi

echo "─────────────────────────────────────────"
echo "$CHANGELOG"
echo "─────────────────────────────────────────"
echo ""

# Build package and verify the wheel installs cleanly (canonical target).
# smoke-install stamps src/monarch_cli/_build_info.json from HEAD before
# building, wipes and rebuilds dist/, and checks the exact --version line.
echo "🔨 Building package and smoke-installing wheel..."
if [[ "$DRY_RUN" == false ]]; then
    rm -rf build/ *.egg-info
    make smoke-install
    uv run twine check dist/*

    # Belt and braces: the artifact we are about to attach must be the version
    # we are about to tag.
    if ! ls dist/monarch_cli-"${VERSION}"-*.whl >/dev/null 2>&1; then
        echo "❌ Built wheel does not match version ${VERSION}."
        echo "   dist/ contains:"
        ls -1 dist/
        echo "   Fix the version metadata and re-run (see RELEASING.md)."
        exit 1
    fi

    # Publish last, from the tagged commit: the stamp the wheel carries must be
    # this exact commit.
    STAMPED_COMMIT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("commit", ""))' src/monarch_cli/_build_info.json)
    if [[ "$STAMPED_COMMIT" != "$(git rev-parse HEAD)" ]]; then
        fail "dist/ was built from ${STAMPED_COMMIT:-no commit}, not HEAD ($(git rev-parse HEAD)); rebuild with make prepublish."
    fi
else
    echo "   [dry-run] Would run: make smoke-install && twine check dist/*"
    echo "   [dry-run] Would require src/monarch_cli/_build_info.json to match HEAD"
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
echo "⚠️  This script does NOT publish to PyPI. Publish LAST, from the same"
echo "   dist/ built from the tagged commit:"
echo ""
echo "   uv run twine upload dist/*"
echo ""
