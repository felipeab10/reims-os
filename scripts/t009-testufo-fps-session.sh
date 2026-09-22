#!/usr/bin/env bash
set -euo pipefail

# Start a repeatable TestUFO workload in the guest and correlate the browser's
# displayed FPS with screenshots from the real Reims vGPU X11 window.
#
# The SSH password is intentionally not stored here. Use an SSH key or provide
# REIMS_T009_SSH_PASSWORD in the environment for a one-shot run.

SSH_HOST="${REIMS_T009_SSH_HOST:-127.0.0.1}"
SSH_PORT="${REIMS_T009_SSH_PORT:-2222}"
SSH_USER="${REIMS_T009_SSH_USER:-felipeab10}"
TEST_URL="${REIMS_T009_TEST_URL:-https://testufo.com/}"
DISPLAY_NUM="${DISPLAY:-:1}"
INTERVAL="${REIMS_T009_CAPTURE_INTERVAL:-5}"
DURATION="${REIMS_T009_CAPTURE_DURATION:-120}"
OUTPUT_DIR="${REIMS_T009_OUTPUT_DIR:-/tmp/reims-t009-testufo-$(date +%Y%m%d-%H%M%S)}"
KNOWN_HOSTS="${REIMS_T009_KNOWN_HOSTS:-/tmp/reims-t009-known_hosts}"
OPEN_URL="${REIMS_T009_OPEN_URL:-1}"

for tool in ssh xwininfo import tesseract; do
    command -v "$tool" >/dev/null || {
        echo "missing required host tool: $tool" >&2
        exit 1
    }
done

if command -v magick >/dev/null; then
    IMAGE_TOOL=(magick)
elif command -v convert >/dev/null; then
    IMAGE_TOOL=(convert)
else
    echo "missing ImageMagick (magick or convert)" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
printf 'timestamp,fps_text,screenshot\n' > "$OUTPUT_DIR/fps.csv"

SSH_OPTIONS=(
    -o StrictHostKeyChecking=no
    -o UserKnownHostsFile="$KNOWN_HOSTS"
    -o ConnectTimeout=10
    -p "$SSH_PORT"
)
if [[ -n "${REIMS_T009_SSH_PASSWORD:-}" ]]; then
    command -v sshpass >/dev/null || {
        echo "REIMS_T009_SSH_PASSWORD requires sshpass" >&2
        exit 1
    }
    SSH_RUN=(env SSHPASS="$REIMS_T009_SSH_PASSWORD" sshpass -e ssh)
else
    SSH_RUN=(ssh)
fi

if [[ "$OPEN_URL" == "1" ]]; then
    echo "Opening $TEST_URL in Safari on $SSH_USER@$SSH_HOST:$SSH_PORT"
    "${SSH_RUN[@]}" "${SSH_OPTIONS[@]}" "$SSH_USER@$SSH_HOST" \
        "osascript -e 'tell application \"Safari\" to activate' -e 'tell application \"Safari\" to open location \"$TEST_URL\"'"
else
    echo "Keeping the currently focused Safari page; no URL navigation requested"
fi

echo "Collecting $DURATION seconds of X11 screenshots every $INTERVAL seconds"
start_epoch="$(date +%s)"
while (( $(date +%s) - start_epoch < DURATION )); do
    timestamp="$(date --iso-8601=seconds)"
    stamp="$(date +%H%M%S)"
    window_id="$(DISPLAY="$DISPLAY_NUM" xwininfo -root -tree 2>/dev/null \
        | awk '/Reims vGPU/ {print $1; exit}')"

    if [[ -n "$window_id" ]]; then
        screenshot="$OUTPUT_DIR/$stamp.png"
        crop="$OUTPUT_DIR/$stamp-fps.png"
        if import -display "$DISPLAY_NUM" -window "$window_id" "$screenshot" 2>/dev/null; then
            # TestUFO places telemetry near the bottom of the page. Keep the
            # upper crop as a fallback for older FPS-test pages.
            "${IMAGE_TOOL[@]}" "$screenshot" -crop 560x120+420+710 -resize 250% \
                -colorspace Gray -threshold 65% "$crop" 2>/dev/null || true
            fps_text="$(tesseract "$crop" stdout --psm 6 2>/dev/null | tr '\n' ' ' \
                | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
            if [[ "$fps_text" != *fps* ]]; then
                "${IMAGE_TOOL[@]}" "$screenshot" -crop 400x100+480+340 -resize 250% \
                    -colorspace Gray -threshold 65% "$crop" 2>/dev/null || true
                fps_text="$(tesseract "$crop" stdout --psm 6 2>/dev/null | tr '\n' ' ' \
                    | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
            fi
            if [[ "$fps_text" != *fps* ]]; then
                # fpstest.vip renders its live FPS and frame-time cards lower
                # in the viewport than TestUFO.
                "${IMAGE_TOOL[@]}" "$screenshot" -crop 620x190+500+690 -resize 250% \
                    -colorspace Gray -threshold 65% "$crop" 2>/dev/null || true
                fps_text="$(tesseract "$crop" stdout --psm 6 2>/dev/null | tr '\n' ' ' \
                    | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
            fi
            printf '%s,%q,%s\n' "$timestamp" "$fps_text" "$screenshot" >> "$OUTPUT_DIR/fps.csv"
        else
            printf '%s,%q,%s\n' "$timestamp" "capture_failed" "" >> "$OUTPUT_DIR/fps.csv"
        fi
    else
        printf '%s,%q,%s\n' "$timestamp" "reims_window_missing" "" >> "$OUTPUT_DIR/fps.csv"
    fi

    sleep "$INTERVAL"
done

echo "Evidence written to $OUTPUT_DIR"
cat "$OUTPUT_DIR/fps.csv"
