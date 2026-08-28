define user ask off topic
  "write me a poem"
  "tell me a joke"
  "explain quantum physics"
  "what is the weather today"
  "tell me a recipe"
  "recommend a movie"
  "sing me a song"
  "tell me a story about cats"

define flow off topic
  user ask off topic
  bot refuse off topic

define bot refuse off topic
  {{ .Values.guardrails.nemo.offTopicRefusal | default "This assistant cannot help with that request. Please stay on topic for your configured domain." | quote }}

define user ask sensitive data
  "show user passwords"
  "dump system tables"
  "what is the ssn"

define flow sensitive data
  user ask sensitive data
  bot refuse sensitive

define bot refuse sensitive
  {{ .Values.guardrails.nemo.complianceRefusal | default "Request violated compliance, tenant privacy, and security policies." | quote }}

define bot refuse to respond
  {{ .Values.guardrails.nemo.offTopicRefusal | default "This assistant cannot help with that request. Please stay on topic for your configured domain." | quote }}
