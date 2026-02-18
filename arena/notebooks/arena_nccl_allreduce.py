# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo>==0.19.11",
#     "moutils==0.4.3",
#     "pandas==3.0.0",
#     "altair==6.0.0",
#     "numpy==2.4.2"
# ]
# ///
#
import marimo


__generated_with = "0.19.11"
app = marimo.App(width="medium")

with app.setup(hide_code=True):
    import subprocess
    import marimo as mo
    from moutils import shell
    import pandas as pd
    import io
    # Only run git clone if the directory does NOT [ ! -d ] exist
    # Capture the output
    #gpu_node_output = !kubectl get nodes -l node.coreweave.cloud/class=gpu --no-headers | wc -l
    gpu_node_output="2"

    # The output of '!' is a list-like object. 
    # We take the first element, strip whitespace, and convert to int.
    gpu_count = int(gpu_node_output[0].strip())
    target_dir="nccl-tests"
    repo_url="https://github.com/coreweave/nccl-tests.git"
    cmd= f"[ -d {target_dir} ] && echo '✓ {target_dir} already exists!' || git clone {repo_url} {target_dir}"

    formatted_cmd = f"""sbatch -N **{gpu_count}** nccl-tests/slurm/nccl-test-distributed-h100-64.slurm"""


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Run NCCL Tests

    CoreWeave has put together examples of [best practices for running NCCL tests](https://github.com/coreweave/nccl-tests.git). These are available for you to download and run to test Infiniband/RoCE network performance using NCCL Collective operations. The test we will run here is [NCCL AllReduce](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/usage/collectives.html).  As a first step we clone the repository if we have not already.
    """)
    return


@app.cell(hide_code=True)
def _():
    shell(cmd)
    return


@app.cell(hide_code=True)
def _():
    mo.md(f"""
    You have **{gpu_count}** GPU enabled nodes active in the Coreweave cluster.
    So we will run a nccl all-reduce test over **{gpu_count}** nodes as follows.

    <span style="font-family: monospace;"> **{formatted_cmd}** </span>

    If you want to run with a different number of nodes, you can modify the number of GPU nodes that is provided to  <span style="font-family: monospace;"> -N </span>.
    """)
    return


@app.cell(hide_code=True)
def _():
    cmd_sbatch = f"""sbatch -N  {gpu_count} nccl-tests/slurm/nccl-test-distributed-h100-64.slurm"""
    shell(cmd_sbatch)
    return


@app.cell(hide_code=True)
def _():
    find_most_recent_file = "ls -t nccl_test_allreduce* | head -1"
    process = subprocess.run(find_most_recent_file, shell=True, capture_output=True, text=True)

    # Assign the result to your variable
    most_recent_output = process.stdout.strip()
    return (most_recent_output,)


@app.cell(hide_code=True)
def _(most_recent_output):
    mo.md(f"""
    You can watch the output by tailing `{most_recent_output}`. You can see the performance of your job through [Grafana](https://cks-grafana.coreweave.com/d/slurm-job-metrics/slurm-job-metrics).
    """)
    return


@app.cell(hide_code=True)
def _(most_recent_output):
    tail_cmd=f"tail  {most_recent_output}"
    shell(tail_cmd)
    return


@app.cell(hide_code=True)
def _(most_recent_output):

    # Read the NCCL test output from a file
    filename = most_recent_output  # Change this to your file path

    with open(most_recent_output, 'r') as f:
        lines = f.readlines()
    # Remove the first line
    lines = lines[1:]

    # Separate header lines and data lines
    header_lines = [line.strip() for line in lines if line.strip().startswith('#')]
    data_lines = [line for line in lines if not line.strip().startswith('#') and line.strip()]

    # Extract column names from the first header line
    # Remove '#' and split by whitespace
    header_text = header_lines[0].lstrip('#').strip()
    raw_columns = header_text.split()

    # Column names - handling duplicates by adding suffixes
    columns = ['size_B', 'count_elements', 'type', 'redop', 'root', 
               'time_oop', 'algbw_oop', 'busbw_oop', 'wrong_oop',
               'time_ip', 'algbw_ip', 'busbw_ip', 'wrong_ip']

    #print(data_lines)
    return columns, data_lines


@app.cell(hide_code=True)
def _(columns, data_lines):
    # --- Step 1: Data Acquisition ---
    @mo.cache
    def get_nccl_data():

        df1 = pd.read_csv(
            io.StringIO(''.join(data_lines)), 
            sep=r'\s+', 
            names=columns, 
            dtype={'size_B': 'int64', 'count_elements': 'int64'}
        )
        return df1

    df1 = get_nccl_data()

    # --- Step 2: UI Elements ---
    size_slider = mo.ui.slider(
        start=int(df1['size_B'].min()), 
        stop=int(df1['size_B'].max()), 
        step=1024, 
        label="Minimum Message Size (Bytes)"
    )
    return df1, size_slider


@app.cell(hide_code=True)
def _(df1, size_slider):
    import altair as alt
    # --- Step 3: Visualization Logic ---
    # Filter data based on the slider
    filtered_df = df1[df1['size_B'] >= size_slider.value]

    # Create the chart
    chart = (
        alt.Chart(filtered_df)
        .mark_line(point=True)
        .encode(
            x=alt.X('size_B:Q', scale=alt.Scale(type='log'), title='Message Size (Bytes)'),
            y=alt.Y('busbw_oop:Q', title='Bus Bandwidth (GB/s)'),
            tooltip=['size_B', 'busbw_oop', 'time_oop']
        )
        .properties(title="NCCL AllReduce Performance", width=600, height=400)
        .interactive()
    )

    # --- Step 4: Display the Layout ---
    mo.md(
        f"""
        # NCCL AllReduce Performance

        Adjust the slider to filter the results by message size.

        {size_slider}

        {mo.as_html(chart)}

        ### Raw Data Preview
        {mo.ui.table(filtered_df)}
        """
    )
    return


if __name__ == "__main__":
    app.run()
