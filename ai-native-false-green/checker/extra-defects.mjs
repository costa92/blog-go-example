// Breakages that are NOT in the platform's own negative list. Each one keeps the
// rendered YAML well-formed but would break or weaken the service once applied.
const w = 'deploy/helm/templates/workload.yaml';
const np = 'deploy/helm/templates/networkpolicy.yaml';

export const extraDefects = () => [
  ['readiness probe on wrong port', w, t => t.replace('readinessProbe: {httpGet: {path: /ready, port: http}', 'readinessProbe: {httpGet: {path: /ready, port: 9090}')],
  ['liveness probe on wrong port', w, t => t.replace('livenessProbe: {httpGet: {path: /health, port: http}', 'livenessProbe: {httpGet: {path: /health, port: 9090}')],
  ['Service targetPort points nowhere', w, t => t.replace('ports: [{name: http, port: 8080, targetPort: http}]', 'ports: [{name: http, port: 8080, targetPort: 9090}]')],
  ['container command replaced by sleep', w, t => t.replace('        imagePullPolicy:', '        command: ["/bin/sleep", "infinity"]\n        imagePullPolicy:')],
  ['Prometheus peer label typo', np, t => t.replace('matchLabels: {app.kubernetes.io/name: prometheus}', 'matchLabels: {app.kubernetes.io/name: prometheus-typo}')],
  ['ingress opened to every pod in monitoring namespace', np, t => t.replace(/      podSelector:\n        matchLabels: \{app.kubernetes.io\/name: prometheus\}\n/, '')],
  ['SA token mounted via projected volume', w, t => t
    .replace('      terminationGracePeriodSeconds: 30', '      volumes: [{name: tok, projected: {sources: [{serviceAccountToken: {path: token}}]}}]\n      terminationGracePeriodSeconds: 30')
    .replace('        ports: [{name: http, containerPort: 8080}]', '        ports: [{name: http, containerPort: 8080}]\n        volumeMounts: [{name: tok, mountPath: /var/run/secrets/tokens}]')],
  ['memory request cut to 1Mi', w, t => t.replace('requests: {cpu: 100m, memory: 128Mi}', 'requests: {cpu: 100m, memory: 1Mi}')],
  ['readiness checked every 300s', w, t => t.replace('readinessProbe: {httpGet: {path: /ready, port: http}, periodSeconds: 5}', 'readinessProbe: {httpGet: {path: /ready, port: http}, periodSeconds: 300}')],
];
