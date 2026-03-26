#!/bin/bash

echo "🚀 Optimizing Jetson for Maximum Performance (Target: 60 FPS)..."

# 1. Set Jetson to MAXN power mode (maximum performance)
echo "Setting power mode to MAXN..."
echo "1" | sudo -S nvpmodel -m 0
echo "1" | sudo -S jetson_clocks

# 2. Verify power mode
echo "--- Current Power Mode ---"
nvpmodel -q

# 3. Check GPU frequency
echo "--- GPU Frequency ---"
cat /sys/devices/gpu.0/devfreq/17000000.gpu/cur_freq

echo "✅ Jetson optimized for maximum performance!"
echo "Note: This will increase power consumption and heat."
