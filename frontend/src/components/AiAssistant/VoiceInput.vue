<template>
  <button
    v-if="isSupported"
    type="button"
    class="voice-btn"
    :class="{ listening: isListening, disabled: disabled }"
    :disabled="disabled"
    @click="toggleListening"
    :aria-label="isListening ? '停止语音输入' : '开始语音输入'"
    :title="isListening ? '停止语音输入' : '语音输入'"
  >
    <svg v-if="!isListening" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
      <line x1="12" y1="19" x2="12" y2="23"/>
      <line x1="8" y1="23" x2="16" y2="23"/>
    </svg>
    <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
      <line x1="12" y1="19" x2="12" y2="23"/>
      <line x1="8" y1="23" x2="16" y2="23"/>
    </svg>
    <span v-if="isListening" class="voice-pulse" />
  </button>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  disabled?: boolean
}>()

const emit = defineEmits<{
  transcript: [text: string]
  listeningChange: [isListening: boolean]
}>()

const isSupported = ref(false)
const isListening = ref(false)

let recognition: any = null

onMounted(() => {
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (SpeechRecognition) {
    isSupported.value = true
    recognition = new SpeechRecognition()
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = 'zh-CN'

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript
      if (transcript) {
        emit('transcript', transcript)
      }
      stopListening()
    }

    recognition.onerror = () => {
      stopListening()
    }

    recognition.onend = () => {
      stopListening()
    }
  }
})

const toggleListening = () => {
  if (isListening.value) {
    stopListening()
  } else {
    startListening()
  }
}

const startListening = () => {
  if (!recognition || isListening.value) return
  try {
    recognition.start()
    isListening.value = true
    emit('listeningChange', true)
  } catch {
    isListening.value = false
  }
}

const stopListening = () => {
  if (!recognition) return
  try {
    recognition.stop()
  } catch {
    // ignore
  }
  isListening.value = false
  emit('listeningChange', false)
}

onUnmounted(() => {
  if (recognition && isListening.value) {
    try {
      recognition.stop()
    } catch {
      // ignore
    }
  }
})
</script>

<style scoped>
.voice-btn {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  border: none;
  background: var(--color-bg-hover);
  color: var(--color-text-disabled);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--button-transition);
  flex-shrink: 0;
  position: relative;
}

.voice-btn:hover:not(:disabled) {
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
}

.voice-btn.listening {
  background: var(--color-error-bg);
  color: #f87171;
  animation: voice-pulse-bg 1.5s ease-in-out infinite;
  box-shadow: var(--shadow-glow-error);
}

.voice-btn.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.voice-pulse {
  position: absolute;
  inset: -4px;
  border-radius: var(--radius-md);
  border: 2px solid rgba(239, 68, 68, 0.4);
  animation: voice-ring 1.5s ease-in-out infinite;
}

@keyframes voice-pulse-bg {
  0%, 100% { background: var(--color-error-bg); }
  50% { background: var(--color-error-hover); }
}

@keyframes voice-ring {
  0% { transform: scale(1); opacity: 1; }
  100% { transform: scale(1.3); opacity: 0; }
}
</style>
