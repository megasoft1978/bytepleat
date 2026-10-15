#!/bin/sh
set -eu
usage() { echo "Usage: $0 --output-dir DIRECTORY" >&2; exit 2; }
[ "$#" -eq 2 ] && [ "$1" = "--output-dir" ] || usage
output_dir=$2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
bundle="$output_dir/BytepleatServices.app"
[ ! -e "$bundle" ] && [ ! -L "$bundle" ] || { echo "Refusing to replace existing bundle: $bundle" >&2; exit 1; }
mkdir -p "$bundle/Contents/MacOS"
cp "$project_dir/integrations/macos/Info.plist" "$bundle/Contents/Info.plist"
swiftc "$project_dir/integrations/macos/BytepleatServices.swift" -framework AppKit -o "$bundle/Contents/MacOS/BytepleatServices"
chmod 755 "$bundle/Contents/MacOS/BytepleatServices"
echo "Built unsigned development service bundle: $bundle"
