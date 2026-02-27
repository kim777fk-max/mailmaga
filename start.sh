#!/bin/bash
cd "$(dirname "$0")"
echo "メルマガいたしん 統合管理ツール を起動中..."
sleep 0.5
open http://localhost:5001
python3 app.py
