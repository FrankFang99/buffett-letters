#!/bin/bash
# 等待构建进程完成，然后自动打包
LOG="/workspace/build.log"
while kill -0 3708 2>/dev/null; do
    sleep 30
done
# 构建完成，检查是否成功
if grep -q "完成!" "$LOG"; then
    cd /workspace
    rm -f 巴菲特分享版.zip
    cd 巴菲特分享版 && zip -r ../巴菲特分享版.zip . -x '*.pyc' '__pycache__/*' 2>/dev/null
    echo "PACK_DONE" >> "$LOG"
else
    echo "BUILD_FAILED" >> "$LOG"
fi
