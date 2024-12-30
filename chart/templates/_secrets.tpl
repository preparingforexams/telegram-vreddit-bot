{{- define "secrets.volume" -}}
name: secrets
secret:
  secretName: cancer-secrets
  items:
    - key: GSA_JSON
      path: ./gsa.json
{{- end }}

{{- define "secrets.volumeMount" -}}
- name: secrets
  mountPath: /gcp
  readOnly: true
{{- end }}
