{{- define "halligalli-observability.labels" -}}
app.kubernetes.io/name: halligalli-observability
app.kubernetes.io/part-of: halligalli
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "halligalli-observability.image" -}}
{{- $image := . -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" $image.digest) -}}
{{- fail "image digest must match sha256:<64 lowercase hex characters>" -}}
{{- end -}}
{{- printf "%s@%s" $image.repository $image.digest -}}
{{- end -}}
