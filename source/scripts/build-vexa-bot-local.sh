#!/usr/bin/env sh
# Build the local Vexa bot image from the checked-in Google Meet join sources.
#
# The Vexa repository's root .dockerignore excludes dist/, so Docker must use a
# deliberately small staging context. Keeping that detail here makes the
# running image reproducible instead of relying on a manually prepared /tmp
# directory.
set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
vexa_dir="$root_dir/vexa"
image_tag=${BROWSER_IMAGE:-meeting-intelligence-vexa-bot:local}
corepack_home=${COREPACK_HOME:-/tmp/vexa-corepack}
stage_dir=$(mktemp -d "${TMPDIR:-/tmp}/meeting-intelligence-vexa-bot.XXXXXX")

cleanup() {
  rm -rf "$stage_dir"
}
trap cleanup EXIT HUP INT TERM

(
  cd "$vexa_dir"
  COREPACK_HOME="$corepack_home" corepack pnpm --filter @vexa/join run build

  mkdir -p "$stage_dir/core/meetings/modules/join"
  cp -a core/meetings/modules/join/dist "$stage_dir/core/meetings/modules/join/dist"

  docker build \
    --build-arg VEXA_IMAGE_VERSION=local-gmeet-no-incognito \
    -t "$image_tag" \
    -f "$vexa_dir/core/meetings/services/bot/Dockerfile.local-patch" \
    "$stage_dir"
)

echo "Built local Vexa bot image: $image_tag"
