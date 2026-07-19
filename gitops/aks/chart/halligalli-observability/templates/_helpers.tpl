{{- define "halligalli-observability.labels" -}}
app.kubernetes.io/name: halligalli-observability
app.kubernetes.io/part-of: halligalli
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "halligalli-observability.image" -}}
{{- $image := . -}}
{{- printf "%s@%s" $image.repository $image.digest -}}
{{- end -}}
