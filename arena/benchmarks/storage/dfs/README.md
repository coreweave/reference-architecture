# Distributed File System Benchmarks

This directory contains benchmarks for distributed file system performance testing.

## Target Systems

- DFS

## Remote Location

During container startup, contents are synced to the login node at:
`/mnt/data/ailabs/benchmarks/storage/dfs/`

## Common Benchmarks

- IOR (Interleaved or Random) benchmark
- mdtest for metadata operations
- fio for I/O workloads
- Sequential and random read/write tests
