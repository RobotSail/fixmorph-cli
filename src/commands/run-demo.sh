#!/bin/bash

set -o pipefail

# Spinner function
spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

# Main function
function run() {
    echo -n " Channeling the force, please wait..."
    python3.11 FixMorph.py --conf=repair.conf --format=unified &> combined-output &
    local pid=$! # ID of the last job running in the background

    # show a spinner while the process is running
    spinner "${pid}"

    wait $pid
    trap "kill $pid 2> /dev/null" EXIT

    # retrieve the patch
    local patch=$(find output/test/ -type f -name "*-generated-patch")
    cp "${patch}" generated.patch

    # clear initial message
    printf "\r\033[K"

    printf "%s\n" "$(cat generated.patch)"
}

run
