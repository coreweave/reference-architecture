import marimo

__generated_with = "0.19.11"
app = marimo.App(width="medium")

with app.setup(hide_code=True):
    import subprocess
    import marimo as mo
    from moutils import shell
    import pandas as pd
    import io
    import os



@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Benchmark VAST Storage

    This is a benchmark for VAST storage using `fio`. This script runs metadata and storage benchmarks on the mounted Vast file system `/mnt/data`.

    The metadata benchmark ("data IO") uses 12 jobs and a 4KB block size to measure IOPS (Input/Output Operations Per Second) and Latency.

    The storage benchmark ("data BW") uses 12 jobs and a 4MB block size to see the highest speed the storage can achieve under a heavy load.

    Compare your output to this example output:
    ```
    Running test: 'data IO'
      write: IOPS=11.2k, BW=43.9MiB/s (46.1MB/s)(2636MiB/60001msec); 0 zone resets
      read: IOPS=48.3k, BW=189MiB/s (198MB/s)(11.1GiB/60002msec)
    Running test: 'data BW'
      write: IOPS=1714, BW=6859MiB/s (7192MB/s)(402GiB/60005msec); 0 zone resets
      read: IOPS=2864, BW=11.2GiB/s (12.0GB/s)(672GiB/60023msec)
    ```
    """)
    return


@app.cell
def _():
    test_cmd="mkdir -p /mnt/data/cw-vast-test && curl -s https://cw-storage.cwobject.com/perf/runtests.sh | bash -s -- -s /mnt/data -f -t /tmp -d cw-vast-test"
    shell(test_cmd)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    To run this test on any other storage device, execute the same command, replacing `/mnt/data` with the Vast data mount and `cw-vast-test` with another directory name within `/mnt/data`.
    """)
    return


if __name__ == "__main__":
    app.run()
