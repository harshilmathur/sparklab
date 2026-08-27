#!/bin/bash
# OS-level inference tuning for DGX Spark (GB10). Run on EACH node, then reboot.
# Credit: trenchnotes.blog/post/os-optimizations-dgx-spark (2026-08-19).
# Verified on our fleet 2026-08-26: idle headroom 3 -> 117 GiB (GUI reclaim),
# TP=2 C12 adversarial aggregate 59.3 -> 60.9 tok/s, zero regression.
# Core layout: 0-4,10-14 = slow (2808 MHz); 5-9,15-19 = fast (3900 MHz).
set -euo pipefail

# 1. OS/systemd/docker onto slow cores; fast cores free for vLLM+NCCL
sudo mkdir -p /etc/systemd/system.conf.d
printf '[Manager]\nCPUAffinity=0-4 10-14\n' | sudo tee /etc/systemd/system.conf.d/cpu-affinity.conf >/dev/null

# 2. NVIDIA/RoCE IRQs onto slow cores (don't steal inference cycles)
sudo tee /etc/systemd/system/irq-affinity.service >/dev/null <<'UNIT'
[Unit]
Description=Set NVIDIA and RoCE IRQ affinity to slow cores
After=multi-user.target
Wants=multi-user.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -c 'for irq in $(grep -iE "nvidia|mlx5|connectx|roce" /proc/interrupts | awk -F: "{print \$1}" | tr -d " "); do echo "0-4,10-14" > /proc/irq/$irq/smp_affinity_list 2>/dev/null; done'
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload && sudo systemctl enable irq-affinity.service

# 3. Headless (reclaim GUI memory — the big win on unified memory)
sudo systemctl set-default multi-user.target

# 4. Swap last-resort + aggressive FS-cache reclaim
printf 'vm.swappiness=1\nvm.vfs_cache_pressure=200\n' | sudo tee /etc/sysctl.d/99-vm-tune.conf >/dev/null

echo "Applied. Add  cpuset: \"5-9,15-19\"  to the vLLM container in your compose, then REBOOT."
