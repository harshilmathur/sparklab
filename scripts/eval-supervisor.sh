#!/bin/bash
# On-box eval supervisor: survives Claude session restarts.
# Watches the GLM lane; on death/timeout -> auto-restore DS4F driver.
# State file: /tmp/eval-state (read it anytime).
S=/tmp/eval-state
note(){ echo "$(date -u +%H:%M:%S) $1" >> $S; }
echo "=== eval-supervisor start $(date -u) ===" > $S
DEADLINE=$(( $(date +%s) + 3000 ))   # 50 min to reach health
while true; do
  if curl -sf -m 3 localhost:8888/v1/models > /dev/null 2>&1; then
    note "HEALTHY - starting 21min hold"
    sleep 1260
    if curl -sf -m 5 localhost:8888/v1/models > /dev/null 2>&1; then
      note "STABLE-AFTER-HOLD - lane ready for battery"
      exit 0
    else
      note "DIED-DURING-HOLD"
      break
    fi
  fi
  # dead-container detection (no restart policy -> exited stays exited)
  ST=$(docker inspect vllm_glm53 --format "{{.State.Status}}" 2>/dev/null)
  if [ "$ST" = "exited" ]; then note "CONTAINER-EXITED"; break; fi
  if [ $(date +%s) -gt $DEADLINE ]; then note "TIMEOUT-50MIN"; break; fi
  sleep 60
done
# FAIL PATH: tear down lane, restore DS4F
note "RESTORING-DS4F"
docker ps -aq | xargs -r docker rm -f > /dev/null 2>&1
ssh -o StrictHostKeyChecking=no <lan-ip> "docker ps -aq | xargs -r docker rm -f" > /dev/null 2>&1
cd ~/tools/mia-dspark-2x && nohup ./start-deepseek-v4-flash-dspark.sh --host 0.0.0.0 > /tmp/mia-launch.log 2>&1 &
for i in $(seq 1 30); do sleep 60; curl -sf -m 3 localhost:8888/v1/models 2>/dev/null | grep -q deepseek && { note "DS4F-RESTORED"; exit 1; }; done
note "DS4F-RESTORE-FAILED-NEEDS-HUMAN"
exit 2
