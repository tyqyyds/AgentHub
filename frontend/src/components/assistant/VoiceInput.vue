<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

defineProps<{
  disabled: boolean
}>()

const emit = defineEmits<{
  result: [text: string]
}>()

const isRecording = ref(false)
const isSupported = ref(false)
const transcript = ref('')

let recognition: SpeechRecognition | null = null

function getSpeechRecognitionCtor(): SpeechRecognitionConstructor | undefined {
  return window.SpeechRecognition || window.webkitSpeechRecognition
}

function checkSupport() {
  isSupported.value = !!getSpeechRecognitionCtor()
}

function toggleRecording() {
  if (isRecording.value) {
    stopRecording()
  } else {
    startRecording()
  }
}

function startRecording() {
  const Ctor = getSpeechRecognitionCtor()
  if (!Ctor) return

  recognition = new Ctor()
  recognition.continuous = false
  recognition.interimResults = false
  recognition.lang = 'zh-CN'

  recognition.onresult = (event: SpeechRecognitionEvent) => {
    const result = event.results[0]
    if (result.isFinal) {
      transcript.value = result[0].transcript
      emit('result', transcript.value)
    }
  }

  recognition.onend = () => {
    isRecording.value = false
  }

  recognition.onerror = () => {
    isRecording.value = false
  }

  recognition.start()
  isRecording.value = true
}

function stopRecording() {
  if (recognition) {
    recognition.stop()
    recognition = null
  }
  isRecording.value = false
}

onMounted(() => {
  checkSupport()
})

onUnmounted(() => {
  stopRecording()
})
</script>

<template>
  <button
    v-if="isSupported"
    class="voice-btn"
    :class="{ recording: isRecording, disabled }"
    :disabled="disabled"
    @click="toggleRecording"
    title="语音输入"
  >
    <div v-if="isRecording" class="wave-animation">
      <span class="wave-bar" />
      <span class="wave-bar" />
      <span class="wave-bar" />
      <span class="wave-bar" />
    </div>
    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  </button>
</template>

<style scoped>
.voice-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  cursor: pointer;
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}

.voice-btn:hover:not(.disabled) {
  background: rgba(var(--color-white-rgb), 0.12);
  color: var(--color-text-secondary);
}

.voice-btn.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.voice-btn.recording {
  background: rgba(255, 77, 79, 0.2);
  color: #ff4d4f;
}

.voice-btn svg {
  width: 18px;
  height: 18px;
}

.wave-animation {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 18px;
}

.wave-bar {
  width: 3px;
  height: var(--spacing-sm);
  background: var(--color-error);
  border-radius: var(--radius-xs);
  animation: wave 1s ease-in-out infinite;
}

.wave-bar:nth-child(1) { animation-delay: 0s; }
.wave-bar:nth-child(2) { animation-delay: 0.15s; }
.wave-bar:nth-child(3) { animation-delay: 0.3s; }
.wave-bar:nth-child(4) { animation-delay: 0.45s; }

@keyframes wave {
  0%, 100% { height: 8px; }
  50% { height: 18px; }
}
</style>
