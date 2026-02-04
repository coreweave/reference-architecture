import marimo

__generated_with = "0.19.4"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import json
    import moterm # auto installs on confirmation
    from ailabs.object_storage_helpers import apply_policy, list_policies, delete_policy, get_s3_client, list_buckets
    return apply_policy, json, list_buckets, list_policies, mo, moterm


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # CoreWeave AI Labs
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## CoreWeave AI Object Storage and LOTA walkthrough and benchmarks
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Create Access Key and Secret Access key in the [console](https://docs.coreweave.com/docs/products/storage/object-storage/get-started-caios)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Set Organizational Policies

    Examples:-

    **Full S3 API access to all users**
    ```
    {
      "policy": {
        "version": "v1alpha1",
        "name": "full-s3-api-access",
        "statements": [
          {
            "name": "allow-full-s3-api-access-to-all",
            "effect": "Allow",
            "actions": [
              "s3:*"
            ],
            "resources": ["*"],
            "principals": ["*"]
          }
        ]
      }
    }
    ```

    **Read-only access to all buckets**
    ```
    {
      "policy": {
        "version": "v1alpha1",
        "name": "s3-read-only-all-buckets",
        "statements": [
          {
            "name": "read-only-access",
            "effect": "Allow",
            "actions": [
              "s3:List*",
              "s3:Get*",
              "s3:Head*"
            ],
            "resources": ["*"],
            "principals": ["*"]
          }
        ]
      }
    }
    ```

    More about [organizational access policies](https://docs.coreweave.com/docs/products/storage/object-storage/auth-access/organization-policies/about)
    """)
    return


@app.cell
def _(apply_policy):
    apply_policy('''
            {
              "policy": {
                "version": "v1alpha1",
                "name": "test_policy_user_full_access",
                "statements": [
                  {
                    "name": "allow-full-access",
                    "effect": "Allow",
                    "actions": ["s3:*"],
                    "resources": ["*"],
                    "principals": ["role/Admin"]
                  }
                ]
              }
            }
            ''')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Query Organizational Access Policies
    """)
    return


@app.cell
def _(json, list_policies):
    policies = list_policies()
    print(json.dumps(policies, indent=2))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### List buckets
    """)
    return


@app.cell
def _(list_buckets):
    list_buckets()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Set Addressing style and Endpoint URL
    """)
    return


@app.cell
def _(moterm):
    moterm.Kmd("aws configure set s3.addressing_style virtual")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Set Endpoint URL

    CAIOS: https://cwobject.com
    LOTA: http://cwlota.com
    """)
    return


@app.cell
def _(moterm):
    moterm.Kmd("aws configure set endpoint_url $S3_ENDPOINT_URL")
    return


@app.cell
def _(moterm):
    moterm.Kmd("aws s3 ls")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Transfer Data
    """)
    return

@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Transfer large amount of data from S3 with parallelism:

    For a few large files, keep --numworkers low and increase --concurrency to maximize multipart upload parallelism:
    ```
    s5cmd --endpoint-url https://cwobject.com \
          --numworkers 4 \
          cp --concurrency 16 's3://source-bucket/*' s3://target-bucket/
    ```

    For many small files, increase --numworkers to maximize parallel file transfers:
    ```
    s5cmd --endpoint-url https://cwobject.com \
          --numworkers 512 \
          cp 's3://source-bucket/*' s3://target-bucket/
    ```
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Benchmark Performance
    """)
    return


if __name__ == "__main__":
    app.run()
