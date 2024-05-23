#!/bin/bash

while true; do
    # Generate a random number between 0 and 1
    random_number=$(awk -v seed=$RANDOM 'BEGIN { srand(seed); print rand() }')

    # Check if the number is greater than 0.8
    if (( $(echo "$random_number > 0.8" | bc -l) )); then
        curl localhost:5000/run

    else
        curl localhost:5000/simulate
    fi

    # Sleep for 5 minutes
    sleep 300
done
