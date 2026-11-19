#!/usr/bin/env bash
set -euo pipefail

: "${RELEASE_IMAGE:?Set RELEASE_IMAGE to a published GHCR digest}"
: "${RELEASE_ID:?Set RELEASE_ID to the workflow run ID and attempt}"
[[ "$RELEASE_IMAGE" =~ ^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$ ]]
[[ "$RELEASE_ID" =~ ^[0-9]{1,20}-[0-9]{1,10}$ ]]

job="higayon-migrate-$RELEASE_ID"
pull_secret=higayon-ghcr
kube=(kubectl --namespace higayon --request-timeout=20s)

# Reuse the app container settings so migrations use its database and runtime
# configuration. A different label keeps the Job out of the app and metrics Services.
"${kube[@]}" get deployment higayon -o json | jq -e \
  --arg image "$RELEASE_IMAGE" --arg job "$job" --arg pull_secret "$pull_secret" '
  .spec.template.spec as $pod |
  ($pod.containers[] | select(.name == "app")) as $app |
  {
    apiVersion: "batch/v1", kind: "Job",
    metadata: {name: $job, labels: {app: "higayon-migration"}},
    spec: {
      backoffLimit: 1,
      activeDeadlineSeconds: 600,
      ttlSecondsAfterFinished: 86400,
      template: {
        metadata: {labels: {app: "higayon-migration"}},
        spec: (($pod | {serviceAccountName, volumes, securityContext}
          | with_entries(select(.value != null))) + {
          restartPolicy: "Never",
          imagePullSecrets: ((($pod.imagePullSecrets // []) + [{name: $pull_secret}]) | unique_by(.name)),
          containers: [($app
            | del(.ports, .livenessProbe, .readinessProbe, .startupProbe, .lifecycle, .args)
            | .image = $image
            | .command = ["python", "manage.py", "migrate", "--noinput"])]
        })
      }
    }
  }' | "${kube[@]}" create -f -

deadline=$((SECONDS + 660))
while true; do
  condition=$("${kube[@]}" get job "$job" -o json |
    jq -r '.status.conditions[]? | select(.status == "True") | .type')
  if [[ "$condition" == *Complete* ]]; then
    break
  fi
  if [[ "$condition" == *Failed* || "$condition" == *FailureTarget* || "$SECONDS" -ge "$deadline" ]]; then
    echo "Migration Job $job failed or timed out" >&2
    "${kube[@]}" logs "job/$job" --all-containers=true --tail=100 || true
    exit 1
  fi
  sleep 3
done

# Set both fields in one update so the new image has pull credentials at rollout.
patch=$(jq -n --arg image "$RELEASE_IMAGE" --arg pull_secret "$pull_secret" '{
  spec: {template: {spec: {
    containers: [{name: "app", image: $image}],
    imagePullSecrets: [{name: $pull_secret}]
  }}}
}')
"${kube[@]}" patch deployment higayon --type=strategic --patch "$patch"
kubectl --namespace higayon rollout status deployment/higayon --timeout=300s
echo "Deployed $RELEASE_IMAGE"
