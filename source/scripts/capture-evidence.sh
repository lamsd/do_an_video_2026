#!/usr/bin/env sh
# Capture reproducible, redaction-safe evidence for Chapter 8 verification.
set -eu

usage() { echo "Usage: $0 {unit|integration} EVID-YYYYMMDD-XXX" >&2; exit 2; }

kind=${1:-}
evidence_id=${2:-}
[ -n "$kind" ] && [ -n "$evidence_id" ] || usage
case "$evidence_id" in *[!A-Za-z0-9_-]*) echo "Unsafe evidence ID" >&2; exit 2;; esac

case "$kind" in
  unit) command='cd "$ROOT/src/backend" && uv run pytest -q' ;;
  integration) command='cd "$ROOT" && ./scripts/verify.sh && ./scripts/smoke-analysis-pipeline.sh' ;;
  *) usage ;;
esac

export ROOT
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
run_dir="$ROOT/evidence/runs/$evidence_id"

if [ -e "$run_dir" ]; then
  echo "Evidence ID already exists: $run_dir" >&2
  exit 2
fi

mkdir -p "$run_dir"
printf '%s\n' "$command" > "$run_dir/commands.txt"
{
  printf 'captured_at_utc='; date -u +%Y-%m-%dT%H:%M:%SZ
  printf 'git_commit='; git -C "$ROOT/.." rev-parse HEAD
  uname -a
  docker --version 2>/dev/null || true
  docker compose version 2>/dev/null || true
  uv --version 2>/dev/null || true
  printf 'working_tree_status=\n'
  git -C "$ROOT/.." status --short
} > "$run_dir/environment.txt"

set +e
sh -c "$command" > "$run_dir/stdout.log" 2>&1
exit_code=$?
set -e
printf '%s\n' "$exit_code" > "$run_dir/exit-code.txt"

if [ "$exit_code" -eq 0 ]; then result=PASS; else result=FAIL; fi
settings_file="$ROOT/settings.env"
setting() {
  key=$1
  awk -F= -v wanted="$key" '$1 == wanted { print substr($0, index($0, "=") + 1); exit }' "$settings_file" 2>/dev/null || true
}
model_version=$(setting MODEL_VERSION)
classifier_adapter=$(setting CLASSIFIER_ADAPTER)
preprocessing_version=$(setting PREPROCESSING_VERSION)
[ -n "$model_version" ] || model_version=baseline-rules-v2
[ -n "$classifier_adapter" ] || classifier_adapter=rules
[ -n "$preprocessing_version" ] || preprocessing_version=2026-09-v1
{
  printf '%s\n\n' '# Evidence manifest'
  printf '%s\n' "- Evidence ID: \`$evidence_id\`"
  printf '%s\n' "- Ngày/giờ (ICT): \`$(TZ=Asia/Ho_Chi_Minh date '+%Y-%m-%d %H:%M:%S %Z')\`"
  printf '%s\n' "- Người chạy: \`${EVIDENCE_OPERATOR:-local-operator}\`"
  printf '%s\n' "- Loại kiểm chứng: \`$kind\`"
  printf '%s\n\n' "- Kết quả: \`$result\`"
  printf '%s\n' '## Phiên bản và môi trường'
  printf '%s\n' "- Git commit: \`$(git -C "$ROOT/.." rev-parse HEAD)\`"
  printf '%s\n' "- Working tree: \`$(if git -C "$ROOT/.." diff --quiet && git -C "$ROOT/.." diff --cached --quiet; then echo clean; else echo dirty; fi)\`"
  printf '%s\n' "- Docker / Compose / uv: xem \`environment.txt\`"
  printf '%s\n' "- \`MODEL_VERSION\`: \`$model_version\`"
  printf '%s\n' "- \`CLASSIFIER_ADAPTER\`: \`$classifier_adapter\`"
  printf '%s\n' "- \`PREPROCESSING_VERSION\`: \`$preprocessing_version\`"
  printf '%s\n\n' '## Dữ liệu và quyền riêng tư'
  if [ "$kind" = unit ]; then
    printf '%s\n' '- Dữ liệu: `none`; unit test không cần transcript.'
  else
    printf '%s\n' '- Dữ liệu: `synthetic`; fixture tự xóa sau run.'
  fi
  printf '%s\n' '- Không lưu secret, raw transcript hay định danh người tham gia trong bundle.'
  printf '%s\n\n' '## Kết luận và giới hạn'
  if [ "$kind" = unit ]; then
    printf '%s\n' '- Test đơn vị xác nhận invariant mã nguồn; không đo chất lượng sentiment hoặc ASR.'
  else
    printf '%s\n' '- Smoke integration xác nhận pipeline nội bộ; không phải Vexa/Google Meet E2E hay Macro-F1.'
  fi
  printf '%s\n' '- Xem `commands.txt`, `stdout.log`, `exit-code.txt` và `environment.txt` để tái lập.'
} > "$run_dir/manifest.md"

exit "$exit_code"
