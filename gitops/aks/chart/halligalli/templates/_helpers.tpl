{{- define "halligalli.labels" -}}
app.kubernetes.io/part-of: halligalli
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Values.releaseVersion | quote }}
{{- end -}}

{{- define "halligalli.selectorLabels" -}}
app.kubernetes.io/name: halligalli
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "halligalli.image" -}}
{{- $image := . -}}
{{- printf "%s@%s" $image.repository $image.digest -}}
{{- end -}}
