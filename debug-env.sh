#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

source .env
# 微信发送配置，强制覆盖避免被其他参数影响
export OPENCLAW_CHANNEL=wechat
export OPENCLAW_ACCOUNT_ID=77cee27e66b3-im-bot
export OPENCLAW_TARGET=o9cq801pNFQu53UfPW03GwVD-QGY@im.wechat
export RUN_ONCE_AND_EXIT=1

echo "Environment after loading:"
env | grep OPENCLAW_
