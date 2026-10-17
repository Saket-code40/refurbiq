#!/bin/bash
# Watchdog: when the fine-tuning process exits, rebuild the six tables and
# refill the docx if the fine-tuned metrics file exists.
cd /home/saket/sentimental_analysis/refurbiq || exit 1
PID="$1"
echo "watchdog waiting on pid $PID at $(date)"
while kill -0 "$PID" 2>/dev/null; do sleep 30; done
echo "finetune process exited at $(date)"
sleep 5
if [ -f research/data/bert_finetuned_metrics.json ]; then
    .venv/bin/python research/scripts/build_tables.py >> research/reports/auto_integration.log 2>&1
    .venv/bin/python research/scripts/update_docx.py >> research/reports/auto_integration.log 2>&1
    date > research/reports/auto_integration.done
    echo "auto-integration finished at $(date)" >> research/reports/auto_integration.log
    echo "AUTO-INTEGRATION COMPLETE"
else
    echo "NO metrics file - training did not complete" | tee -a research/reports/auto_integration.log
fi
