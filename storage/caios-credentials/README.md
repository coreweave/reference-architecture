This script can be used to configure CoreWeave credentials to use the AWS CLI. It creates two profiles, local for use on the local machine, and cw for use with lota.

Prerequesites: 
- A KUBECONFIG for a CoreWeave cluster for a user who has cwobject:createaccesskey permissions.
- curl, jq, kubectl should be installed. 

The output will be to configure `~/.coreweave/cw.credentials` and `~/.coreweave/cw.config` (if they do not already exist) as follows, with a newly obtained CAIOS key. 

Contents of `~/.coreweave/cw.config`. This creates two profiles, each with a different endpoint_url. The cwlota endpoint should be used whenever working on CoreWeave GPU infrastructure. The cwobject endpoint can be used whenever you need to access data from somewhere else. 

```
[cw]
endpoint_url = https://cwlota.com
s3 =
    addressing_style = virtual
[profile local]
endpoint_url = https://cwobject.com
s3 =
    addressing_style = virtual
```

Contents of `~/.corewave/cw.credentials`. Note that the access key and secret access key will be unique to your user id and should be protected like any credentials. 

```
[cw]
aws_access_key_id = CWACCESSKEYID
aws_secret_access_key = cwsecretaccesskeyidlongstring
output = json
[local]
aws_access_key_id = CWACCESSKEYID
aws_secret_access_key = cwsecretaccesskeyidlongstring
output = json
```