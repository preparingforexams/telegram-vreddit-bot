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
{{- end }}


{{- define "downloads.nodeAffinity" -}}
requiredDuringSchedulingIgnoredDuringExecution:
  nodeSelectorTerms:
    - matchExpressions:
        - key: node-role.kubernetes.io/control-plane
          operator: In
          values:
            - "true"
{{- end }}
