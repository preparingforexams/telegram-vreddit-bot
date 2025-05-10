{{- define "secrets.volume" -}}
name: gsa-json
secret:
  secretName: gsa
{{- end }}

{{- define "secrets.volumeMount" -}}
name: gsa-json
mountPath: /gcp
readOnly: true
{{- end }}
