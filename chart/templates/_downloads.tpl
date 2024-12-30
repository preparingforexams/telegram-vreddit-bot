{{- define "downloads.volume" -}}
name: downloads
ephemeral:
  volumeClaimTemplate:
    spec:
      storageClassName: {{ .Values.scratch.storageclass }}
      accessModes:
        - ReadWriteOnce
      resources:
        requests:
          storage: {{ .Values.scratch.size }}
{{- end -}}
