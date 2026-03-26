#!/bin/bash

echo "🔍 Searching for libcusparseLt on entire system..."

# 1. Search in all standard library paths
echo "--- Searching in /usr/lib ---"
find /usr/lib -name "*cusparseLt*" 2>/dev/null

echo "--- Searching in /usr/local ---"
find /usr/local -name "*cusparseLt*" 2>/dev/null

echo "--- Searching in /opt ---"
find /opt -name "*cusparseLt*" 2>/dev/null

# 2. Check what CUDA packages are installed
echo "--- Installed CUDA packages ---"
dpkg -l | grep -i cuda | grep -i sparse

# 3. Check LD_LIBRARY_PATH
echo "--- Current LD_LIBRARY_PATH ---"
echo $LD_LIBRARY_PATH

# 4. Check ldconfig cache
echo "--- Libraries in ldconfig cache ---"
ldconfig -p | grep -i cusparse

echo "--- Done ---"
