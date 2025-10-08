#!/bin/bash
# Generate Word documents from Markdown with proper table formatting

echo "Generating Word documents with native tables..."

# Function to process a markdown file
process_md_file() {
    md_file=$1
    docx_file=$2

    echo "Processing: $md_file -> $docx_file"

    # Create temp file for preprocessing
    temp_file="${md_file}.temp"

    # Preprocess: Extract tables from code blocks
    python3 -c "
import re

with open('$md_file', 'r', encoding='utf-8') as f:
    content = f.read()

# Simple pattern: remove code block markers around tables only
pattern = r'\`\`\`\n((?:[^\n]*\|[^\n]*\n?)+)\n?\`\`\`'

def clean_table(match):
    table_text = match.group(1)
    # Remove any non-table lines like [Browser closed...]
    lines = [line for line in table_text.split('\n') if '|' in line or line.strip().startswith('-')]
    return '\n'.join(lines)

modified_content = re.sub(pattern, clean_table, content)

with open('$temp_file', 'w', encoding='utf-8') as f:
    f.write(modified_content)
"

    # Convert with pandoc
    pandoc "$temp_file" -o "$docx_file" \
        --toc --toc-depth=2 \
        --wrap=none \
        -f markdown+pipe_tables+simple_tables+multiline_tables+grid_tables \
        -t docx

    # Enhance tables
    python3 enhance_word_tables.py "$docx_file"

    # Clean up temp file
    rm -f "$temp_file"
}

# Process root level files
process_md_file "README.md" "Word/README.docx"
process_md_file "START_HERE.md" "Word/START_HERE.docx"
process_md_file "INDEX.md" "Word/INDEX.docx"
process_md_file "IMPLEMENTATION_PLAN.md" "Word/IMPLEMENTATION_PLAN.docx"
process_md_file "DOCUMENTATION_SUMMARY.md" "Word/DOCUMENTATION_SUMMARY.docx"
process_md_file "DOCUMENTATION_IMPROVEMENTS.md" "Word/DOCUMENTATION_IMPROVEMENTS.docx"

# Process subfolder files
process_md_file "01_EXECUTIVE_SUMMARY/executive_summary.md" "Word/01_EXECUTIVE_SUMMARY/executive_summary.docx"
process_md_file "02_BUSINESS_ANALYSIS/VIDEO_TRACKING_SCENARIOS_GUIDE.md" "Word/02_BUSINESS_ANALYSIS/VIDEO_TRACKING_SCENARIOS_GUIDE.docx"
process_md_file "02_BUSINESS_ANALYSIS/VISUAL_GUIDE_CLOSING_EVENTS.md" "Word/02_BUSINESS_ANALYSIS/VISUAL_GUIDE_CLOSING_EVENTS.docx"
process_md_file "03_DEVELOPMENT/CODE_DOCUMENTATION_GUIDE.md" "Word/03_DEVELOPMENT/CODE_DOCUMENTATION_GUIDE.docx"
process_md_file "03_DEVELOPMENT/INTERVAL_MERGING_EXPLAINED.md" "Word/03_DEVELOPMENT/INTERVAL_MERGING_EXPLAINED.docx"
process_md_file "04_TESTING/README.md" "Word/04_TESTING/README.docx"
process_md_file "04_TESTING/TEST_SCENARIOS_COMPLETE.md" "Word/04_TESTING/TEST_SCENARIOS_COMPLETE.docx"
process_md_file "05_REFERENCE/GETTING_STARTED.md" "Word/05_REFERENCE/GETTING_STARTED.docx"
process_md_file "05_REFERENCE/QUICK_REFERENCE_CARD.md" "Word/05_REFERENCE/QUICK_REFERENCE_CARD.docx"
process_md_file "05_REFERENCE/quick_reference_guide.md" "Word/05_REFERENCE/quick_reference_guide.docx"

echo ""
echo "✓ All Word documents generated successfully!"
