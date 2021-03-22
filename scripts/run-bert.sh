#!/bin/bash

LOGDIR="./lightning_logs_bert_stsb_mar15"
rm -rf "$LOGDIR"
mkdir -p "$LOGDIR"

pwsh ./scripts/train-bert.ps1 --logdir $LOGDIR > "$LOGDIR/output.log" 2>&1
