#!/bin/bash

#SBATCH --nodes 1
#SBATCH --ntasks-per-node 8
#SBATCH --gpus-per-node 8
#SBATCH --constraint gpu
#SBATCH --job-name test
#SBATCH --output test.%j
#SBATCH --export all
#SBATCH --exclusive

export NCCL_SOCKET_IFNAME=eth0
export SHARP_COLL_ENABLE_PCI_RELAXED_ORDERING=1
export NCCL_COLLNET_ENABLE=0
export NCCL_IB_HCA=ibp
export UCX_NET_DEVICES=ibp0:1,ibp1:1,ibp2:1,ibp3:1,ibp4:1,ibp5:1,ibp6:1,ibp7:1

export MASTER_PORT="$(expr 10000 + "$(echo -n "${SLURM_JOB_ID:?}" | tail -c 4)")"
export MASTER_ADDR="$(scontrol show hostnames "${SLURM_JOB_NODELIST:?}" | head -n 1)"

# This will be used for both the output directory as well as the wandb project
export PROJECT_NAME="test"

# If you change this, make sure the --container-mount can find it
export OUTDIR="/mnt/data/coreweave/${PROJECT_NAME}"

# Megatron's dataset indices will go here once built
export CACHEDIR="${OUTDIR}/cache"

# save images here
export CONTAINER_DIR="/mnt/data/coreweave/images"

# uncomment if running on H100/H200
#CPU_BIND='map_ldom:0,0,0,0,1,1,1,1'


# Use squished container if available, otw download and save it.
export REMOTE_IMAGE_URI="ghcr.io#coreweave/ml-containers/megatron-demo:dmarx-megatron-demo-7773da7"
export IMAGE_NAME="training-test.sqsh"
export LOCAL_IMAGE_PATH="${CONTAINER_DIR}/${IMAGE_NAME}"

CONTAINER_SAVE=""
if [ -f "$LOCAL_IMAGE_PATH" ]; then
  CONTAINER_IMAGE="${LOCAL_IMAGE_PATH}"
else
  CONTAINER_IMAGE="${REMOTE_IMAGE_URI}"
  CONTAINER_SAVE="--container-save=${LOCAL_IMAGE_PATH}"
fi


srun --container-image "${CONTAINER_IMAGE}" "${CONTAINER_SAVE}" \
     --container-mounts /mnt/data:/mnt/data \
     --export=ALL \
     --mpi=pmix \
     --kill-on-bad-exit=1 \
     ${CPU_BIND:+"--cpu-bind=$CPU_BIND"} \
     bash <<'EOF'
#### in-line srun script ####
#!/bin/bash

export CUDA_DEVICE_MAX_CONNECTIONS=1
export MEGATRON_TENSORIZER_SYNCHRONOUS=0
export MEGATRON_TENSORIZER_SERIALIZATION_NUM_THREADS=5
export MEGATRON_TENSORIZER_PROFILE_SAVE=0

export WORLD_SIZE="${SLURM_NTASKS:?}"
export RANK="${SLURM_PROCID:?}"
export LOCAL_RANK="${SLURM_LOCALID:?}"
export CUDA_DEVICE_ORDER='PCI_BUS_ID'


CKPTDIR_LOAD="${CKPTDIR_LOAD:-${OUTDIR}/checkpoints}"
CKPTDIR_SAVE="${CKPTDIR_SAVE:-${OUTDIR}/checkpoints}"
mkdir -p "${CKPTDIR_SAVE}"


touch "${CKPTDIR_SAVE}/progress.txt"


cd /usr/src/app/megatron-lm

WARNING_FILTERS=(
'-Wignore::DeprecationWarning'
'-Wignore::FutureWarning'
'-Wignore::UserWarning:megatron.core.tensor_parallel.layers'  # "async_grad_allreduce is deprecated"
'-Wignore::UserWarning:megatron.core.optimizer.distrib_optimizer'  # "pre_hook" method deprecations
)

python3 "${WARNING_FILTERS[@]:?}" \
        "/usr/src/app/megatron-lm/pretrain_gpt.py" \
        --wandb-exp-name "${SLURM_JOB_ID:?}/megatron-test" \
        --wandb-project "${PROJECT_NAME}" \
        --wandb-save-dir "${OUTDIR}/logs" \
        --tensorboard-dir "${OUTDIR}/tensorboard" \
        --data-cache-path ${CACHEDIR} \
        --load "${CKPTDIR_LOAD}" \
        --save "${CKPTDIR_SAVE}" \
        --save-interval 3500 \
        --tensor-model-parallel-size 4 \
        --pipeline-model-parallel-size 1 \
        --context-parallel-size 1 \
        --sequence-parallel \
        --overlap-grad-reduce \
        --overlap-param-gather \
        --train-iters 2507400 \
        --lr 4e-06 \
        --min-lr 4e-07 \
        --lr-warmup-iters 2000 \
        --lr-decay-iters 2507400 \
        --lr-decay-style cosine \
        --clip-grad 1.0 \
        --bf16 \
        --use-flash-attn \
        --rotary-seq-len-interpolation-factor 32 \
        --no-fp8-wgrad \
        --use-distributed-optimizer \
        --distributed-backend nccl \
        --split 949,50,1 \
        --seed 42 \
        --use-checkpoint-args \
        --no-masked-softmax-fusion \
        --attention-softmax-in-fp32 \
        --transformer-impl transformer_engine \
        --attention-dropout 0.0 \
        --hidden-dropout 0.0 \
        --rotary-base 500000 \
        --rotary-percent 1.0 \
        --use-rope-scaling \
        --micro-batch-size 1 \
        --log-interval 1 \
        --tensorboard-log-interval 1 \
        --eval-interval 100 \
        --eval-iters 10 \
        --logging-level 20 \
        --log-params-norm \
        --log-num-zeros-in-grad \
        --log-throughput \
        --log-progress \
        --timing-log-level 0 \
        --timing-log-option all \
        --log-timers-to-tensorboard \
        --log-validation-ppl-to-tensorboard \
        --log-memory-to-tensorboard \
        --log-world-size-to-tensorboard \
        --ffn-hidden-size 11008 \
        --num-attention-heads 32 \
        --num-layers 32 \
        --hidden-size 4096 \
        --seq-length 8192 \
        --max-position-embeddings 8192 \
        --untie-embeddings-and-output-weights \
        --normalization RMSNorm \
        --swiglu \
        --position-embedding-type rope \
        --disable-bias-linear \
        --group-query-attention \
        --num-query-groups 8 \
        --data-path \
          /usr/src/app/megatron-lm/coreweave-datasets/smol/tokenized/nerdstash_v2-uint16/chunk.0 \
          /usr/src/app/megatron-lm/coreweave-datasets/smol/tokenized/nerdstash_v2-uint16/chunk.0 \
        --tokenizer-type GPTSentencePieceTokenizer \
        --tokenizer-model /usr/src/app/megatron-lm/tokenizers/nerdstash-tokenizer-v2/tokenizer.model \
        --dataloader-type cyclic
EOF
