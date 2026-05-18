#!/bin/bash
#SBATCH --job-name=raytest
#SBATCH --nodes=2
#SBATCH --exclusive
#SBATCH --tasks-per-node=1 # we will launch one worker task per node
#SBATCH --cpus-per-task=8  # each worker task gets 8 CPUs. Adjust as needed.
#SBATCH --mem-per-cpu=1GB  # each cpu gets 1GB of memory. Adjust as needed.
#SBATCH --gpus-per-task=8  # each worker task will use 8 GPUs. Adjust as needed.
#SBATCH --time=1-00:00:00 # specify a time limit of one day


# Here we activate a conda environment named "rayenv" to load Ray and its dependencies.

eval "$(conda shell.bash hook)"
conda activate rayenv
# Getting the node names
nodes=$(scontrol show hostnames "$SLURM_JOB_NODELIST")
nodes_array=($nodes)

head_node=${nodes_array[0]}
head_node_ip=$(srun --nodes=1 --ntasks=1 -w "$head_node" hostname --ip-address)


# Obtain the head node's IP address. We use this so that when we start worker nodes we can connect them to the head node.
# if we detect a space character in the head node IP, we'll
# convert it to an ipv4 address. This step is optional.
if [[ "$head_node_ip" == *" "* ]]; then
IFS=' ' read -ra ADDR <<<"$head_node_ip"
if [[ ${#ADDR[0]} -gt 16 ]]; then
  head_node_ip=${ADDR[1]}
else
  head_node_ip=${ADDR[0]}
fi
echo "IPV6 address detected. We split the IPV4 address as $head_node_ip"
fi
# If multiple users are going to be starting Ray clusters, we need to make
# sure that the clusters do not conflict. 
# Please see https://docs.ray.io/en/latest/cluster/vms/user-guides/community/slurm.html#slurm-networking-caveats
# for more information. So, make sure slurm users create a unique set of ports following that pattern. 
# Start the head node using one node, one task, and explicitly set the number of CPUs and GPUs on that node.
# Launch this in the background so that we can continue to start worker nodes.
port=6379
node_manager_port=6700
object_manager_port=6701
ray_client_server_port=10001
redis_shard_ports=6702
min_worker_port=10002
max_worker_port=19999

ip_head=$head_node_ip:$port
export ip_head
echo "IP Head: $ip_head"

echo "Starting HEAD at $head_node"
srun --nodes=1 --ntasks=1 -w "$head_node" \
    ray start --head --node-ip-address="$head_node_ip" \
        --port=$port \
        --node-manager-port=$node_manager_port \
        --object-manager-port=$object_manager_port \
        --ray-client-server-port=$ray_client_server_port \
        --redis-shard-ports=$redis_shard_ports \
        --min-worker-port=$min_worker_port \
        --max-worker-port=$max_worker_port \
        --num-cpus "${SLURM_CPUS_PER_TASK}" --num-gpus 8 --block &


# optional, though may be useful in certain versions of Ray < 1.0.
sleep 10

# number of nodes other than the head node
worker_num=$((SLURM_JOB_NUM_NODES - 1))

for ((i = 1; i <= worker_num; i++)); do
    node_i=${nodes_array[$i]}
    echo "Starting WORKER $i at $node_i"
    srun --nodes=1 --ntasks=1 -w "$node_i" \
        ray start --address "$ip_head" \
        --num-cpus "${SLURM_CPUS_PER_TASK}" --num-gpus 8 --block &
    sleep 5
done

# sleep to keep the job running until any time limit specified using #SBATCH directives is reached.
# This just means that the job will not exit immediately after starting the Ray cluster, so you
# can use it interactively. 
sleep inf
