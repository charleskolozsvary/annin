#!/bin/bash

script_name="corrinline"

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

echo "This script should only be run while inside the top-level tex-pdf-edits directory."
read -p "Would you like to proceed? (yes/no): " answer

if [ "$answer" != "yes" ]; then
    echo "Exiting."
    exit 0
fi

pixi install

cat <<EOF > "$script_name"
#!/bin/bash
pixi run --manifest-path "$PWD" python -m texpdfedits.inlinecorr "\$@"
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
