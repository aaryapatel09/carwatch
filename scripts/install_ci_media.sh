#!/usr/bin/env bash
set -euo pipefail

# Bound stalled mirror requests; the workflow also caps this step at five minutes.
apt_options=(-o Acquire::Retries=2 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30)
sudo env DEBIAN_FRONTEND=noninteractive apt-get "${apt_options[@]}" update
sudo env DEBIAN_FRONTEND=noninteractive apt-get "${apt_options[@]}" install -y --no-install-recommends ffmpeg libgl1
