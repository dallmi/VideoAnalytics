#!/bin/bash

# Script to create Word2 folder with Word-optimized markdown and docx files
# This preserves original .md and Word/ files untouched

echo "Creating Word2 documentation..."

# List of files to process (relative paths)
files=(
    "README.md"
    "START_HERE.md"
    "INDEX.md"
    "IMPLEMENTATION_PLAN.md"
    "DOCUMENTATION_SUMMARY.md"
    "DOCUMENTATION_IMPROVEMENTS.md"
    "01_EXECUTIVE_SUMMARY/executive_summary.md"
    "02_BUSINESS_ANALYSIS/VISUAL_GUIDE_CLOSING_EVENTS.md"
    "02_BUSINESS_ANALYSIS/VIDEO_TRACKING_SCENARIOS_GUIDE.md"
    "04_TESTING/README.md"
    "04_TESTING/TEST_SCENARIOS_COMPLETE.md"
    "05_REFERENCE/GETTING_STARTED.md"
    "05_REFERENCE/QUICK_REFERENCE_CARD.md"
    "05_REFERENCE/quick_reference_guide.md"
)

# Add 03_DEVELOPMENT to Word2 structure if needed
mkdir -p Word2/03_DEVELOPMENT

# Process each file
for file in "${files[@]}"; do
    if [[ -f "$file" ]]; then
        echo "Processing $file..."

        # Determine output path
        if [[ "$file" == *"/"* ]]; then
            # File in subfolder
            dirname=$(dirname "$file")
            basename=$(basename "$file" .md)
            word_optimized="Word2/${dirname}/${basename}_WORD.md"
            output_docx="Word2/${dirname}/${basename}.docx"
        else
            # Root level file
            basename=$(basename "$file" .md)
            word_optimized="Word2/${basename}_WORD.md"
            output_docx="Word2/${basename}.docx"
        fi

        # Create directory if it doesn't exist
        mkdir -p "$(dirname "$word_optimized")"

        # Copy and process markdown file
        # Replace ASCII art patterns with markdown tables
        python3 -c "
import re
import sys

with open('$file', 'r') as f:
    content = f.read()

# Replace ASCII boxes with structured text
# Pattern 1: Box drawings with ┌┐└┘├┤
content = re.sub(r'```\s*\n[┌├└╔╠╚].*?\n```', '', content, flags=re.DOTALL)

# Pattern 2: Simple ASCII art boxes (preserve structure as text)
def convert_ascii_box(match):
    box_content = match.group(0)
    # Remove box drawing characters
    cleaned = re.sub(r'[┌┐└┘├┤─│═║╔╗╚╝╠╣]', '', box_content)
    # Clean up extra whitespace
    lines = [line.strip() for line in cleaned.split('\n') if line.strip()]
    return '\n'.join(lines)

# Remove code blocks with ASCII boxes
content = re.sub(r'\`\`\`[^\n]*\n[^`]*[┌├└╔╠╚║═][^`]*\`\`\`', convert_ascii_box, content, flags=re.DOTALL)

with open('$word_optimized', 'w') as f:
    f.write(content)
"

        # Convert to Word with pandoc
        pandoc "$word_optimized" \
            -o "$output_docx" \
            --toc \
            --toc-depth=2 \
            -f markdown+pipe_tables \
            -t docx \
            --columns=1000

        # Apply table formatting
        python3 enhance_word_tables.py "$output_docx"

        echo "✓ Created $output_docx"
    else
        echo "⚠ File not found: $file"
    fi
done

echo ""
echo "Word2 documentation creation complete!"
echo "Total files processed: ${#files[@]}"
