#!/usr/bin/env bash
# Build script for Render — installs ffmpeg + Python deps
set -e

apt-get update -y && apt-get install -y ffmpeg
pip install --upgrade pip
pip install -r requirements.txt
