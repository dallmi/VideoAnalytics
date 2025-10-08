#!/bin/bash
# Regenerate all Word documents with proper table formatting
# This script processes each file individually to ensure all tables are converted

echo "=== Regenerating All Word Documents with Enhanced Tables ==="
echo ""

# Counter for tracking
total=0
success=0
failed=0

# Function to process a single markdown file
process_file() {
    local md_file=$1
    local docx_file=$2

    total=$((total + 1))
    echo "[$total] Processing: $md_file"

    # Convert with pandoc
    if pandoc "$md_file" -o "$docx_file" \
        --toc --toc-depth=2 \
        -f markdown+pipe_tables+simple_tables+multiline_tables+grid_tables \
        -t docx 2>&1; then

        # Enhance tables
        if python3 enhance_word_tables.py "$docx_file" 2>&1; then
            success=$((success + 1))
            echo "    ✓ Success"
        else
            failed=$((failed + 1))
            echo "    ✗ Failed to enhance tables"
        fi
    else
        failed=$((failed + 1))
        echo "    ✗ Failed to convert"
    fi
    echo ""
}

# Process all files
echo "Processing root-level files..."
process_file "README.md" "Word/README.docx"
process_file "START_HERE.md" "Word/START_HERE.docx"
process_file "INDEX.md" "Word/INDEX.docx"
process_file "IMPLEMENTATION_PLAN.md" "Word/IMPLEMENTATION_PLAN.docx"
process_file "DOCUMENTATION_SUMMARY.md" "Word/DOCUMENTATION_SUMMARY.docx"
process_file "DOCUMENTATION_IMPROVEMENTS.md" "Word/DOCUMENTATION_IMPROVEMENTS.docx"

echo "Processing subfolder files..."
process_file "01_EXECUTIVE_SUMMARY/executive_summary.md" "Word/01_EXECUTIVE_SUMMARY/executive_summary.docx"
process_file "02_BUSINESS_ANALYSIS/VIDEO_TRACKING_SCENARIOS_GUIDE.md" "Word/02_BUSINESS_ANALYSIS/VIDEO_TRACKING_SCENARIOS_GUIDE.docx"
process_file "02_BUSINESS_ANALYSIS/VISUAL_GUIDE_CLOSING_EVENTS.md" "Word/02_BUSINESS_ANALYSIS/VISUAL_GUIDE_CLOSING_EVENTS.docx"
process_file "03_DEVELOPMENT/CODE_DOCUMENTATION_GUIDE.md" "Word/03_DEVELOPMENT/CODE_DOCUMENTATION_GUIDE.docx"
process_file "03_DEVELOPMENT/INTERVAL_MERGING_EXPLAINED.md" "Word/03_DEVELOPMENT/INTERVAL_MERGING_EXPLAINED.docx"
process_file "04_TESTING/README.md" "Word/04_TESTING/README.docx"
process_file "04_TESTING/TEST_SCENARIOS_COMPLETE.md" "Word/04_TESTING/TEST_SCENARIOS_COMPLETE.docx"
process_file "05_REFERENCE/GETTING_STARTED.md" "Word/05_REFERENCE/GETTING_STARTED.docx"
process_file "05_REFERENCE/QUICK_REFERENCE_CARD.md" "Word/05_REFERENCE/QUICK_REFERENCE_CARD.docx"
process_file "05_REFERENCE/quick_reference_guide.md" "Word/05_REFERENCE/quick_reference_guide.docx"

echo "=== Summary ==="
echo "Total files: $total"
echo "Successful: $success"
echo "Failed: $failed"
echo ""
echo "✓ Done!"
