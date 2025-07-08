#!/bin/bash

SHARD=$(printf "shard_%02d" ${SLURM_PROCID})

/opt/bitnami/rclone/bin/rclone \
    --config=<WORK_DIR>/local-rclone.conf \
    copy caios:<BUCKET_NAME> <DESTINATION_PATH> \
    --files-from=<WORK_DIR>/shards/${SHARD} \
    --ignore-existing \
    --fast-list \
    --transfers=128 \
    --checkers=256 \
    --multi-thread-streams=12 \
    --multi-thread-cutoff=64M \
    --buffer-size=32M \
    --progress --stats=600s
