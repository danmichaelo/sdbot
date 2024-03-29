#!/bin/bash

echo "=== This is SDBot running on $(hostname) ===" >> sdbot.log

. www/python/venv/bin/activate
sdbot

sed -n "$(grep -n === sdbot.log | tail -n 1 | sed 's/\([0-9]*\).*/\1/'),\$p" sdbot.log > last.log

