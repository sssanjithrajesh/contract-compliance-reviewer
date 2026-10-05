{{- define "ccr.name" -}}{{ .Chart.Name }}{{- end }}
{{- define "ccr.fullname" -}}{{ printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}{{- end }}
{{- define "ccr.labels" -}}
app.kubernetes.io/name: {{ include "ccr.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
{{- define "ccr.env" -}}
- name: CCR_CUSTOMER
  value: {{ .Values.customer | quote }}
- name: CCR_OFFLINE
  value: {{ ternary "1" "0" .Values.offline | quote }}
- name: CCR_BASE_URL
  value: {{ .Values.app.baseUrl | quote }}
{{- if .Values.app.reviewer }}
- name: CCR_REVIEWER
  value: {{ .Values.app.reviewer | quote }}
{{- end }}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ default (printf "%s-db" (include "ccr.fullname" .)) .Values.database.existingSecret }}
      key: DATABASE_URL
{{- range $key, $env := dict "anthropicApiKey" "ANTHROPIC_API_KEY" "hubspotToken" "HUBSPOT_PRIVATE_APP_TOKEN" "slackWebhookUrl" "SLACK_WEBHOOK_URL" "slackSigningSecret" "SLACK_SIGNING_SECRET" }}
- name: {{ $env }}
  valueFrom:
    secretKeyRef:
      name: {{ include "ccr.fullname" $ }}-secrets
      key: {{ $env }}
      optional: true
{{- end }}
{{- end }}
