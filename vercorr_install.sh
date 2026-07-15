#!/bin/bash

main_name=$(grep -m 1 '^\[project.scripts\]' -A 1 pyproject.toml | grep '=' | sed 's/=.*//' | tr -d '[:space:]')

script_name="vercorr"

if [ -z "$1" ]; then
    echo "Error: no destination directory provided"
    exit 1
fi

if [ ! -d "$1" ]; then
    echo "Error: '$1' is not a valid directory"
    exit 1
fi

if ! command -v pixi &> /dev/null; then
    echo "Error: pixi not found. Please install pixi and make sure it is on your PATH."
    exit 1
fi  

echo "This script should only be run while inside the top-level $main_name directory (the one that contains this file)."
read -p "Would you like to proceed? (yes/no): " answer

if [ "$answer" != "yes" ]; then
    echo "Exiting."
    exit 0
fi

pixi install

cat <<EOF > "$script_name"
#!/bin/bash
pixi run --manifest-path "$PWD" $script_name "\$@"
EOF

chmod +x "$script_name"

if cp "$script_name" "$1"; then
    rm "$script_name"
    echo "Installed. Run '$script_name -h' to verify."
else
    echo "Error: Failed to copy '$script_name' to '$1'."
    exit 1
fi

exit 0
