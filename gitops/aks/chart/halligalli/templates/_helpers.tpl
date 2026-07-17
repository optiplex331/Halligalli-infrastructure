{{- define "halligalli.labels" -}}
app.kubernetes.io/part-of: halligalli
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ required "releaseVersion is required" .Values.releaseVersion | quote }}
{{- end -}}

{{- define "halligalli.selectorLabels" -}}
app.kubernetes.io/name: halligalli
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "halligalli.image" -}}
{{- $image := . -}}
{{- $repository := required "image repository is required" $image.repository -}}
{{- $digest := required "image digest is required" $image.digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" $digest) -}}
{{- fail "image digest must match sha256:<64 lowercase hex characters>" -}}
{{- end -}}
{{- printf "%s@%s" $repository $digest -}}
{{- end -}}

{{- define "halligalli.validateValues" -}}
{{- if not (regexMatch "^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$" .Values.ingress.host) -}}
{{- fail "ingress.host must be a DNS hostname" -}}
{{- end -}}
{{- end -}}
