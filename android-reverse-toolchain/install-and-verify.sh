#!/usr/bin/env bash
set -euo pipefail
# Usage: bash install-and-verify.sh <offline_bundle_directory> [target_apk]
BASE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$BASE/tools"
JAVA="$(command -v java || true)"
if [ -z "$JAVA" ]; then echo 'ERROR: Java 17 or 21 required.' >&2; exit 2; fi
if [ ! -x "$BASE/jadx/bin/jadx" ]; then
  unzip -q -o "$TOOL/jadx-1.5.6.zip" -d "$BASE/jadx"
fi
echo '=== JVM ==='
java -version 2>&1 | head -3
echo '=== JADX ==='
bash "$BASE/jadx/bin/jadx" --version
echo '=== Apktool ==='
java -jar "$TOOL/apktool_3.0.3.jar" --version
echo '=== Baksmali ==='
java -jar "$TOOL/baksmali-3.0.10-fat-release.jar" --help | head -8
echo '=== Smali ==='
java -jar "$TOOL/smali-3.0.10-fat-release.jar" --help | head -8
if [ "$#" -ge 1 ]; then
  APK="$1"
  test -f "$APK"
  mkdir -p "$BASE/output"
  echo '=== APK resources/manifest ==='
  java -Xmx3g -jar "$TOOL/apktool_3.0.3.jar" decode --force --no-src --output "$BASE/output/resources" "$APK"
  echo '=== DEX targeted smali ==='
  unzip -p "$APK" classes10.dex > "$BASE/output/classes10.dex"
  java -Xmx3g -jar "$TOOL/baksmali-3.0.10-fat-release.jar" disassemble "$BASE/output/classes10.dex" -o "$BASE/output/classes10_smali"
  echo '=== Target JADX decompile on classes10.dex ==='
  bash "$BASE/jadx/bin/jadx" --no-res -j 2 -d "$BASE/output/classes10_java" "$BASE/output/classes10.dex"
fi
