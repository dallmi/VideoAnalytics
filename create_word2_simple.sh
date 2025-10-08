#!/bin/bash

# Simple script to create Word2 folder with direct markdown to Word conversion
# This preserves original .md and Word/ files untouched

echo "Creating Word2 documentation (simple approach)..."

# List of files to process (relative paths from root)
files=(
    "README.md"
    "START_HERE.md"
    "INDEX.md"
    "IMPLEMENTATION_PLAN.md"
    "DOCUMENTATION_SUMMARY.md"
    "DOCUMENTATION_IMPROVEMENTS.md"
    "01_EXECUTIVE_SUMMARY/executive_summary.md"
    "02_BUSINESS_ANALYSIS/VISUAL_GUIDE_CLOSING_EVENTS.md"
    "02_BUSINESS_ANALYSIS/VIDEO_TRACKING_SCENARIOS_GUIDE_WORD.md"
    "04_TESTING/README.md"
    "04_TESTING/TEST_SCENARIOS_COMPLETE.md"
    "05_REFERENCE/GETTING_STARTED.md"
    "05_REFERENCE/QUICK_REFERENCE_CARD.md"
    "05_REFERENCE/quick_reference_guide.md"
)

success_count=0
fail_count=0

# Process each file
for file in "${files[@]}"; do
    if [[ -f "$file" ]]; then
        echo "Processing $file..."

        # Determine output path in Word2
        if [[ "$file" == *"/"* ]]; then
            # File in subfolder
            dirname=$(dirname "$file")
            basename=$(basename "$file" .md)
            output_docx="Word2/${dirname}/${basename}.docx"
        else
            # Root level file
            basename=$(basename "$file" .md)
            output_docx="Word2/${basename}.docx"
        fi

        # Create directory if it doesn't exist
        mkdir -p "$(dirname "$output_docx")"

        # Convert directly to Word with pandoc
        if pandoc "$file" \
            -o "$output_docx" \
            --toc \
            --toc-depth=2 \
            -f markdown+pipe_tables \
            -t docx \
            --columns=1000 2>&1; then

            # Apply table formatting
            if python3 enhance_word_tables.py "$output_docx" 2>&1 | grep -q "Enhanced"; then
                echo "✓ Created $output_docx"
                ((success_count++))
            else
                echo "⚠ Created $output_docx (table formatting may have failed)"
                ((success_count++))
            fi
        else
            echo "✗ Failed to convert $file"
            ((fail_count++))
        fi
    else
        echo "⚠ File not found: $file"
        ((fail_count++))
    fi
done

echo ""
echo "==============================================="
echo "Word2 documentation creation complete!"
echo "✓ Success: $success_count files"
echo "✗ Failed: $fail_count files"
echo "==============================================="
