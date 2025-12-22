This script can be used to configure CoreWeave credentials to use the AWS CLI. It creates two profiles, cw for use on the local machine, and default for use with lota.

Prerequesites: 
- A KUBECONFIG for a CoreWeave cluster for a user who has cwobject:createaccesskey permissions.
- curl, jq, kubectl should be installed. 