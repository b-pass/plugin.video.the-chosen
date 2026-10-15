#!/bin/sh
# Build the installable zip for a tagged version and attach it to a draft GitHub release.
#
#   ./make-release.sh [version] [title]
#
# version defaults to the one in addon.xml and must already be tagged (and pushed).
# Kodi needs the zip's top-level directory to be the addon id, which GitHub's own
# source download doesn't do, so it's built here with git archive from the tag.
set -eu

ADDON_ID=plugin.video.the-chosen
cd "$(dirname "$0")"

VERSION=${1:-$(sed -n 's/^ *version="\([^"]*\)".*/\1/p' addon.xml | head -n1)}
TITLE=${2:-$VERSION}

if ! git rev-parse -q --verify "refs/tags/$VERSION" >/dev/null; then
    echo "No tag $VERSION; tag and push it first" >&2
    exit 1
fi
if ! git show "$VERSION:addon.xml" | grep -q "version=\"$VERSION\""; then
    echo "addon.xml at tag $VERSION doesn't say version=\"$VERSION\"" >&2
    exit 1
fi

OUT=$(mktemp -d)
ZIP="$OUT/$ADDON_ID-$VERSION.zip"
git archive --format=zip --prefix="$ADDON_ID/" -o "$ZIP" "$VERSION" -- . \
    ':(exclude)*.md' ':(exclude)make-release.sh'
unzip -l "$ZIP"

gh release create "$VERSION" "$ZIP" --draft --verify-tag --title "$TITLE" --notes ""
echo "Draft created with $ZIP; add notes and publish it on GitHub."
